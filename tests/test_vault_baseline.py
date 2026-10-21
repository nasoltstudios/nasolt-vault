"""Headless regression tests. All vaults and passwords here are synthetic."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Set this before importing vault, whose default path is resolved at import time.
_IMPORT_HOME = tempfile.TemporaryDirectory(prefix="nasolt_test_import_", dir=ROOT / "tests")
os.environ["NASOLT_DATA_DIR"] = _IMPORT_HOME.name

from nasolt_vault import crypto  # noqa: E402
from nasolt_vault import export  # noqa: E402
from nasolt_vault import vault  # noqa: E402


MASTER = "synthetic-master-password-only"
SECRET = "synthetic-entry-password-only"


class VaultBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_test_vault_", dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.vault_path = os.path.join(self.temp.name, "vault.enc")
        patch_dir = mock.patch.object(vault, "VAULT_DIR", self.temp.name)
        patch_file = mock.patch.object(vault, "VAULT_FILE", self.vault_path)
        patch_dir.start()
        patch_file.start()
        self.addCleanup(patch_file.stop)
        self.addCleanup(patch_dir.stop)

    def _new_session_with_entry(self):
        session = vault.VaultSession()
        self.addCleanup(session.close)
        session.create(MASTER)
        entries = [vault._default_entry(title="Synthetic", password=SECRET)]
        session.save(entries, [])
        return session, entries

    def test_create_unlock_and_wrong_password(self):
        session = vault.VaultSession()
        self.addCleanup(session.close)
        session.create(MASTER)
        self.assertTrue(vault.vault_exists())
        session.close()
        self.assertEqual(vault.VaultSession().open(MASTER), ([], []))
        with self.assertRaises(ValueError):
            vault.VaultSession().open("incorrect-synthetic-password")

    def test_crypto_round_trip_and_fresh_nonce(self):
        key = crypto.derive_key(MASTER, os.urandom(crypto.SALT_SIZE))
        plaintext = b"synthetic plaintext"
        nonce, tag, ciphertext = crypto.encrypt_aes_gcm(plaintext, key)
        self.assertEqual(crypto.decrypt_aes_gcm(nonce, tag, ciphertext, key), plaintext)
        nonce2, _, _ = crypto.encrypt_aes_gcm(plaintext, key)
        self.assertNotEqual(nonce, nonce2)

    def test_tampered_ciphertext_and_tag_rejected(self):
        session, _ = self._new_session_with_entry()
        session.close()
        original = Path(self.vault_path).read_bytes()
        for offset in (crypto.VAULT_FILE_HEADER_LEN - 1, len(original) - 1):
            with self.subTest(offset=offset):
                changed = bytearray(original)
                changed[offset] ^= 1
                Path(self.vault_path).write_bytes(changed)
                with self.assertRaises(ValueError):
                    vault.VaultSession().open(MASTER)
        Path(self.vault_path).write_bytes(original)

    def test_save_reload_and_backup_contains_prior_generation(self):
        session, entries = self._new_session_with_entry()
        entries.append(vault._default_entry(title="Second", password="synthetic-second"))
        session.save(entries, [])
        session.close()
        self.assertEqual(len(vault.VaultSession().open(MASTER)[0]), 2)
        backup = Path(self.vault_path + ".bak")
        self.assertTrue(backup.is_file())
        with mock.patch.object(vault, "VAULT_FILE", str(backup)):
            self.assertEqual(len(vault.VaultSession().open(MASTER)[0]), 1)

    def test_replace_failure_keeps_primary_and_backup_can_be_opened(self):
        session, entries = self._new_session_with_entry()
        before = Path(self.vault_path).read_bytes()
        entries.append(vault._default_entry(title="Unsaved", password="synthetic-unsaved"))
        with mock.patch.object(vault.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaises(OSError):
                session.save(entries, [])
        self.assertEqual(Path(self.vault_path).read_bytes(), before)
        with mock.patch.object(vault, "VAULT_FILE", self.vault_path + ".bak"):
            self.assertEqual(len(vault.VaultSession().open(MASTER)[0]), 0)

    def test_fsync_failure_keeps_primary(self):
        session, entries = self._new_session_with_entry()
        before = Path(self.vault_path).read_bytes()
        entries.append(vault._default_entry(title="Unsaved", password="synthetic-unsaved"))
        with mock.patch.object(vault.os, "fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaises(OSError):
                session.save(entries, [])
        self.assertEqual(Path(self.vault_path).read_bytes(), before)

    def test_explicit_backup_recovery_after_primary_corruption(self):
        session, _ = self._new_session_with_entry()
        session.close()
        damaged = b"corrupt synthetic primary"
        Path(self.vault_path).write_bytes(damaged)
        with self.assertRaises(ValueError):
            vault.VaultSession().open(MASTER)
        recovery = vault.VaultSession()
        self.addCleanup(recovery.close)
        self.assertEqual(recovery.recover_from_backup(MASTER, confirmed=True), ([], []))
        self.assertEqual(len(list(Path(self.temp.name).glob("vault.enc.pre-recovery-*"))), 1)

    def test_legacy_bare_list_payload_compatibility(self):
        salt = os.urandom(crypto.SALT_SIZE)
        key = crypto.derive_key(MASTER, salt)
        legacy = [{"id": "legacy-synthetic", "title": "Legacy", "password": SECRET}]
        nonce, tag, ciphertext = crypto.encrypt_aes_gcm(json.dumps(legacy).encode(), key)
        Path(self.vault_path).write_bytes(crypto.build_vault_blob(salt, nonce, tag, ciphertext))
        session = vault.VaultSession()
        entries, groups = session.open(MASTER)
        self.assertEqual((entries, groups), (legacy, []))
        session.save(entries, groups)
        session.close()
        self.assertEqual(vault.VaultSession().open(MASTER), (legacy, []))

    def test_malformed_vault_rejected(self):
        cases = [b"", b"wrong-magic" + bytes(100), crypto.MAGIC + bytes([99]) + bytes(100)]
        for raw in cases:
            with self.subTest(raw=raw[:5]):
                Path(self.vault_path).write_bytes(raw)
                with self.assertRaises(ValueError):
                    vault.VaultSession().open(MASTER)

    def test_corrupted_authenticated_payload_rejected(self):
        salt = os.urandom(crypto.SALT_SIZE)
        key = crypto.derive_key(MASTER, salt)
        nonce, tag, ciphertext = crypto.encrypt_aes_gcm(b"not JSON", key)
        Path(self.vault_path).write_bytes(crypto.build_vault_blob(salt, nonce, tag, ciphertext))
        with self.assertRaises(vault.VaultFormatError):
            vault.VaultSession().open(MASTER)

    def test_import_export_round_trip_json_and_csv(self):
        entries = [vault._default_entry(title="Synthetic", username="example", password=SECRET, group_id="g1")]
        groups = [{"id": "g1", "name": "Synthetic group"}]
        for fmt in ("JSON", "CSV"):
            with self.subTest(fmt=fmt):
                path = export.export_vault(entries, fmt, self.temp.name, groups)
                rows = export.read_import_file(path)
                fresh_entries, fresh_groups = [], []
                result = export.merge_import(fresh_entries, fresh_groups, rows)
                self.assertEqual((result.added, result.groups_created), (1, 1))
                self.assertEqual(fresh_entries[0]["password"], SECRET)
                self.assertEqual(fresh_groups[0]["name"], "Synthetic group")
                self.assertEqual(export.merge_import(fresh_entries, fresh_groups, rows).skipped, 1)

    def test_encrypted_export_import_and_authentication(self):
        entries = [vault._default_entry(title="Synthetic", username="example", password=SECRET, group_id="g1")]
        groups = [{"id": "g1", "name": "Synthetic group"}]
        password = "synthetic-export-passphrase-42"
        first = export.export_vault(entries, "NVE", self.temp.name, groups, password=password)
        second = export.export_vault(entries, "NVE", self.temp.name, groups, password=password)
        self.assertNotEqual(first, second)
        blob = Path(first).read_bytes()
        self.assertTrue(blob.startswith(export.ENCRYPTED_MAGIC))
        self.assertNotIn(SECRET.encode(), blob)
        self.assertNotEqual(blob, Path(second).read_bytes())
        rows = export.read_import_file(first, password=password)
        fresh_entries, fresh_groups = [], []
        merged = export.merge_import(fresh_entries, fresh_groups, rows)
        self.assertEqual((merged.added, merged.groups_created), (1, 1))
        self.assertEqual(fresh_entries[0]["password"], SECRET)
        self.assertEqual(fresh_groups[0]["name"], "Synthetic group")

        with self.assertRaisesRegex(ValueError, "password"):
            export.read_import_file(first)
        with self.assertRaisesRegex(ValueError, "Decryption failed"):
            export.read_import_file(first, password="incorrect-synthetic-password")
        for offset in (len(blob) - 1, len(export.ENCRYPTED_MAGIC) + crypto.SALT_SIZE):
            corrupted = bytearray(blob)
            corrupted[offset] ^= 1
            path = Path(self.temp.name, f"tampered_{offset}.nve")
            path.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError, "Decryption failed"):
                export.read_import_file(str(path), password=password)
        truncated = Path(self.temp.name, "truncated.nve")
        truncated.write_bytes(blob[:10])
        with self.assertRaises(ValueError):
            export.read_import_file(str(truncated), password=password)

        before = set(Path(self.temp.name).glob("*.nve"))
        with mock.patch.object(export.os, "fsync", side_effect=OSError("synthetic failure")):
            with self.assertRaisesRegex(OSError, "no completed export"):
                export.export_vault(entries, "NVE", self.temp.name, groups, password=password)
        self.assertEqual(set(Path(self.temp.name).glob("*.nve")), before)

    def test_bad_import_rejected(self):
        path = Path(self.temp.name, "bad.json")
        path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            export.read_import_file(str(path))


if __name__ == "__main__":
    unittest.main()
