"""Phase 1B data-integrity tests using only disposable synthetic vaults."""

import json
import datetime
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import test_vault_baseline as baseline

MASTER, ROOT, SECRET = baseline.MASTER, baseline.ROOT, baseline.SECRET
crypto, export, vault = baseline.crypto, baseline.export, baseline.vault


class IntegrityRecoveryTests(unittest.TestCase):
    setUp = baseline.VaultBaselineTests.setUp
    _new_session_with_entry = baseline.VaultBaselineTests._new_session_with_entry

    def _authenticated_payload(self, payload):
        salt = os.urandom(crypto.SALT_SIZE)
        key = crypto.derive_key(MASTER, salt)
        plaintext = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        nonce, tag, ciphertext = crypto.encrypt_aes_gcm(plaintext, key)
        raw = crypto.build_vault_blob(salt, nonce, tag, ciphertext)
        Path(self.vault_path).write_bytes(raw)
        return raw

    def test_invalid_payloads_rejected_without_rewrite(self):
        invalid = [None, {}, {"entries": []}, {"entries": [], "groups": None},
                   {"entries": {}, "groups": []}, {"entries": [None], "groups": []},
                   {"entries": [{}], "groups": []},
                   {"entries": [{"id": "a", "title": "t", "password": 4}], "groups": []},
                   {"entries": [{"id": "a", "title": "t", "password": SECRET, "group_id": 5}], "groups": []},
                   {"entries": [{"id": "a", "title": "t", "password": SECRET},
                                {"id": "a", "title": "u", "password": SECRET}], "groups": []},
                   {"entries": [], "groups": [{}]},
                   b'{"entries": [',
                   b'{"entries": [], "entries": [], "groups": []}',
                   b'{"entries": [], "groups": [], "extra": NaN}']
        for payload in invalid:
            with self.subTest(kind=str(type(payload)), payload_index=invalid.index(payload)):
                raw = self._authenticated_payload(payload)
                with self.assertRaises(vault.VaultFormatError) as raised:
                    vault.VaultSession().open(MASTER)
                self.assertNotIn(SECRET, str(raised.exception))
                self.assertEqual(Path(self.vault_path).read_bytes(), raw)
                self.assertFalse(Path(self.vault_path + ".bak").exists())

    def test_valid_empty_and_legacy_optional_fields(self):
        for payload in ([], {"entries": [], "groups": []},
                        [{"id": "legacy", "title": "Synthetic", "password": SECRET, "custom": {"x": 1}}]):
            with self.subTest(payload_type=type(payload).__name__):
                self._authenticated_payload(payload)
                session = vault.VaultSession()
                entries, groups = session.open(MASTER)
                self.assertEqual(entries, payload if isinstance(payload, list) else [])
                self.assertEqual(groups, [])
                session.close()

    def test_second_writer_blocked_and_released_on_close(self):
        holder = vault.VaultSession()
        self.addCleanup(holder.close)
        holder.create(MASTER)
        other = vault.VaultSession()
        with self.assertRaises(vault.VaultBusyError):
            other.open(MASTER)
        holder.close()
        other.open(MASTER)
        other.close()

    def test_separate_process_blocked_and_crash_releases_lock(self):
        owner = vault.VaultSession()
        self.addCleanup(owner.close)
        owner.create(MASTER)
        env = dict(os.environ, NASOLT_DATA_DIR=self.temp.name)
        script = ("import vault,sys; s=vault.VaultSession(); "
                  "\ntry: s.open('synthetic-master-password-only')\n"
                  "except vault.VaultBusyError: sys.exit(7)\n"
                  "else: s.close(); sys.exit(0)")
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 7)
        owner.close()

        marker = Path(self.temp.name, "child-ready")
        hold_script = ("import vault,time,pathlib; s=vault.VaultSession(); "
                       "s.open('synthetic-master-password-only'); "
                       "pathlib.Path('child-ready').write_text('ready'); time.sleep(30)")
        child = subprocess.Popen([sys.executable, "-c", hold_script], cwd=self.temp.name,
                                 env={**env, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(marker.exists(), "child did not acquire the synthetic vault lock")
            with self.assertRaises(vault.VaultBusyError):
                vault.VaultSession().open(MASTER)
        finally:
            child.kill()
            child.wait(timeout=10)
        reopened = vault.VaultSession()
        # Windows can briefly retain the killed process's byte-range lock
        # after wait() returns. The lock must become available promptly.
        deadline = time.monotonic() + 3
        while True:
            try:
                reopened.open(MASTER)
                break
            except vault.VaultBusyError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        reopened.close()

    def test_external_modification_blocks_save_and_preserves_backup(self):
        session, entries = self._new_session_with_entry()
        backup_before = Path(self.vault_path + ".bak").read_bytes()
        Path(self.vault_path).write_bytes(b"synthetic external modification")
        with self.assertRaises(vault.VaultConflictError):
            session.save(entries, [])
        self.assertEqual(Path(self.vault_path + ".bak").read_bytes(), backup_before)
        self.assertEqual(Path(self.vault_path).read_bytes(), b"synthetic external modification")

    def test_interrupted_save_stages_preserve_primary(self):
        session, entries = self._new_session_with_entry()
        primary = Path(self.vault_path).read_bytes()
        backup = Path(self.vault_path + ".bak").read_bytes()
        entries.append(vault._default_entry(title="Unsaved", password=SECRET))
        real_write = vault._write_temp
        for failed_call in (1, 2):
            calls = [0]
            def fail_at(raw):
                calls[0] += 1
                if calls[0] == failed_call:
                    raise OSError("synthetic stage failure")
                return real_write(raw)
            with self.subTest(failed_call=failed_call):
                with mock.patch.object(vault, "_write_temp", side_effect=fail_at):
                    with self.assertRaises(OSError):
                        session.save(entries, [])
                self.assertEqual(Path(self.vault_path).read_bytes(), primary)
                self.assertEqual(Path(self.vault_path + ".bak").read_bytes(), backup)
                self.assertEqual(list(Path(self.temp.name).glob(".vault-*.tmp")), [])

    def test_primary_replace_failure_preserves_verified_old_copy(self):
        session, entries = self._new_session_with_entry()
        primary = Path(self.vault_path).read_bytes()
        entries.append(vault._default_entry(title="Unsaved", password=SECRET))
        real_replace = vault.os.replace
        def fail_primary(src, dst):
            if dst == self.vault_path:
                raise OSError("synthetic primary replacement failure")
            return real_replace(src, dst)
        with mock.patch.object(vault.os, "replace", side_effect=fail_primary):
            with self.assertRaises(OSError):
                session.save(entries, [])
        self.assertEqual(Path(self.vault_path).read_bytes(), primary)
        self.assertEqual(Path(self.vault_path + ".bak").read_bytes(), primary)
        self.assertEqual(list(Path(self.temp.name).glob(".vault-*.tmp")), [])

    def test_recovery_requires_confirmation_and_preserves_original(self):
        session, _ = self._new_session_with_entry()
        session.close()
        damaged = b"synthetic damaged primary"
        Path(self.vault_path).write_bytes(damaged)
        self.assertTrue(vault.backup_is_valid(MASTER))
        with self.assertRaises(PermissionError):
            vault.VaultSession().recover_from_backup(MASTER)
        recovered = vault.VaultSession()
        self.addCleanup(recovered.close)
        entries, groups = recovered.recover_from_backup(MASTER, confirmed=True)
        self.assertEqual((entries, groups), ([], []))
        preserved = list(Path(self.temp.name).glob("vault.enc.pre-recovery-*"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_bytes(), damaged)
        recovered.close()
        reopened = vault.VaultSession()
        self.assertEqual(reopened.open(MASTER), ([], []))
        reopened.close()

    def test_failed_recovery_does_not_replace_primary(self):
        session, _ = self._new_session_with_entry()
        session.close()
        damaged = b"synthetic damaged primary"
        Path(self.vault_path).write_bytes(damaged)
        Path(self.vault_path + ".bak").write_bytes(b"synthetic bad backup")
        self.assertFalse(vault.backup_is_valid(MASTER))
        with self.assertRaises(vault.VaultFormatError):
            vault.VaultSession().recover_from_backup(MASTER, confirmed=True)
        self.assertEqual(Path(self.vault_path).read_bytes(), damaged)
        self.assertFalse(list(Path(self.temp.name).glob("vault.enc.pre-recovery-*")))

    def test_recovery_refuses_valid_primary_and_wrong_password(self):
        session, _ = self._new_session_with_entry()
        session.close()
        primary = Path(self.vault_path).read_bytes()
        self.assertFalse(vault.backup_is_valid("wrong-synthetic-master"))
        with self.assertRaises(vault.VaultConflictError):
            vault.VaultSession().recover_from_backup(MASTER, confirmed=True)
        self.assertEqual(Path(self.vault_path).read_bytes(), primary)
        self.assertFalse(list(Path(self.temp.name).glob("vault.enc.pre-recovery-*")))

    def test_recovery_replace_failure_preserves_primary_and_backup(self):
        session, _ = self._new_session_with_entry()
        session.close()
        damaged = b"synthetic damaged primary"
        Path(self.vault_path).write_bytes(damaged)
        backup = Path(self.vault_path + ".bak").read_bytes()
        with mock.patch.object(vault.os, "replace", side_effect=OSError("synthetic recovery failure")):
            with self.assertRaises(OSError):
                vault.VaultSession().recover_from_backup(MASTER, confirmed=True)
        self.assertEqual(Path(self.vault_path).read_bytes(), damaged)
        self.assertEqual(Path(self.vault_path + ".bak").read_bytes(), backup)
        self.assertEqual(len(list(Path(self.temp.name).glob("vault.enc.pre-recovery-*"))), 1)

    def test_create_replacement_preserves_old_encrypted_bytes(self):
        session, _ = self._new_session_with_entry()
        session.close()
        old = Path(self.vault_path).read_bytes()
        new_session = vault.VaultSession()
        self.addCleanup(new_session.close)
        new_session.create("synthetic-new-master")
        preserved = list(Path(self.temp.name).glob("vault.enc.replaced-*"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_bytes(), old)
        with self.assertRaises(FileExistsError):
            vault.create_vault("synthetic-another-master")

    def test_repeated_exports_never_overwrite_and_failed_export_cleans_up(self):
        entries = [vault._default_entry(title="Synthetic", password=SECRET)]
        class FrozenDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 2, 3, 4, 5)
        for fmt in ("JSON", "CSV"):
            with self.subTest(fmt=fmt):
                with mock.patch.object(export.datetime, "datetime", FrozenDatetime):
                    first = export.export_vault(entries, fmt, self.temp.name)
                    first_bytes = Path(first).read_bytes()
                    second = export.export_vault(entries, fmt, self.temp.name)
                self.assertNotEqual(first, second)
                self.assertEqual(Path(first).read_bytes(), first_bytes)
                self.assertEqual(export.read_import_file(second)[0]["password"], SECRET)
        before = set(Path(self.temp.name).glob("nasolt_vault_export_*"))
        with mock.patch.object(export.os, "fsync", side_effect=OSError("synthetic export failure")):
            with self.assertRaises(OSError) as raised:
                export.export_vault(entries, "JSON", self.temp.name)
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertEqual(set(Path(self.temp.name).glob("nasolt_vault_export_*")), before)
