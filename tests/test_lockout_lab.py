"""Lockout Lab tests use synthetic names and disposable encrypted files."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_vault_baseline as baseline
from nasolt_vault.lockout_lab import LabError, LabStore, add_node, add_route, circular_nodes, empty_model, simulate

vault = baseline.vault
MASTER = baseline.MASTER


class GraphTests(unittest.TestCase):
    def test_and_requirements_and_or_alternative(self):
        model = empty_model()
        phone = add_node(model, "Phone", "device", "phone", "documented")
        email = add_node(model, "Email", "account", "primary_email", "documented")
        codes = add_node(model, "Backup codes", "method", evidence="documented")
        account = add_node(model, "Bank", "account")
        add_route(model, account, [phone, email])
        self.assertEqual(next(x for x in simulate(model, "lost_phone") if x["id"] == account)["status"], "blocked")
        add_route(model, account, [codes])
        result = next(x for x in simulate(model, "lost_phone") if x["id"] == account)
        self.assertEqual(result["status"], "available")
        self.assertIn("modeled", result["reason"].lower())
        self.assertEqual(next(x for x in simulate(model, "primary_email") if x["id"] == account)["status"], "available")

    def test_lost_computer_and_unknown_dependencies(self):
        model = empty_model()
        computer = add_node(model, "Computer", "device", "computer", "documented")
        missing = add_node(model, "Unmapped method", "method")
        account = add_node(model, "Account", "account")
        add_route(model, account, [computer, missing])
        result = next(x for x in simulate(model, "lost_computer") if x["id"] == account)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["unknown"])
        model["nodes"] = [n for n in model["nodes"] if n["id"] != missing]
        result = next(x for x in simulate(model, "lost_phone") if x["id"] == account)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["missing_references"], [missing])

    def test_cycle_and_independent_alternative(self):
        model = empty_model()
        a = add_node(model, "Email", "account")
        b = add_node(model, "Identity account", "account")
        codes = add_node(model, "Printed codes", "method", evidence="verified")
        add_route(model, a, [b])
        add_route(model, b, [a])
        self.assertEqual(circular_nodes(model), {a, b})
        self.assertEqual(next(x for x in simulate(model, "lost_phone") if x["id"] == a)["status"], "unknown")
        add_route(model, a, [codes])
        result = next(x for x in simulate(model, "lost_phone") if x["id"] == b)
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["circular"])

    def test_no_account_route_is_unknown_and_bad_schema_rejected(self):
        model = empty_model()
        add_node(model, "Account", "account", evidence="verified")
        self.assertEqual(simulate(model, "lost_phone")[0]["status"], "unknown")
        model["nodes"][0]["kind"] = []
        with self.assertRaises(LabError):
            simulate(model, "lost_phone")
        model["nodes"][0]["kind"] = "account"
        model["nodes"][0]["password"] = "synthetic-secret-value"
        with self.assertRaises(LabError):
            simulate(model, "lost_phone")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_lab_", dir=baseline.ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "vault.enc"
        patch_dir = mock.patch.object(vault, "VAULT_DIR", self.temp.name)
        patch_file = mock.patch.object(vault, "VAULT_FILE", str(self.file))
        patch_dir.start(); patch_file.start()
        self.addCleanup(patch_file.stop); self.addCleanup(patch_dir.stop)
        self.session = vault.VaultSession()
        self.addCleanup(self.session.close)
        self.session.create(MASTER)
        self.store = LabStore(self.session)

    def test_encrypted_round_trip_and_session_lock(self):
        model = self.store.load()
        add_node(model, "Synthetic email account", "account")
        self.store.save(model)
        raw = self.store.path.read_bytes()
        self.assertNotIn(b"Synthetic email account", raw)
        self.assertEqual(LabStore(self.session).load(), model)
        self.session.close()
        with self.assertRaises(RuntimeError):
            self.store.save(model)
        self.assertEqual(self.store.path.read_bytes(), raw)
        reopened = vault.VaultSession()
        self.addCleanup(reopened.close)
        reopened.open(MASTER)
        self.assertEqual(LabStore(reopened).load(), model)

    def test_tamper_corruption_and_backup_preservation(self):
        first = self.store.load()
        add_node(first, "First", "account")
        self.store.save(first)
        first_raw = self.store.path.read_bytes()
        second = {"version": 1, "nodes": [dict(n) for n in first["nodes"]]}
        add_node(second, "Second", "method", evidence="documented")
        self.store.save(second)
        self.assertEqual(Path(str(self.store.path) + ".bak").read_bytes(), first_raw)
        damaged = bytearray(self.store.path.read_bytes())
        damaged[-1] ^= 1
        self.store.path.write_bytes(damaged)
        with self.assertRaises(LabError):
            LabStore(self.session).load()
        self.assertEqual(self.store.path.read_bytes(), bytes(damaged))
        self.assertEqual(Path(str(self.store.path) + ".bak").read_bytes(), first_raw)
        with self.assertRaises(PermissionError):
            self.store.recover_from_backup()
        restored = self.store.recover_from_backup(confirmed=True)
        self.assertEqual(restored, first)
        self.assertEqual(self.store.path.read_bytes(), first_raw)
        self.assertEqual(len(list(Path(self.temp.name).glob("lockout_lab.enc.pre-recovery-*"))), 1)

    def test_save_conflict_and_failure_keep_prior_bytes(self):
        model = self.store.load()
        add_node(model, "One", "account")
        self.store.save(model)
        before = self.store.path.read_bytes()
        add_node(model, "Two", "account")
        with mock.patch("nasolt_vault.lockout_lab.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.store.save(model)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.store.path.write_bytes(before + b"synthetic change")
        with self.assertRaises(LabError):
            self.store.save(model)

    def test_authenticated_malformed_lab_and_new_vault_key_are_rejected(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from nasolt_vault.lockout_lab import MAGIC

        nonce = os.urandom(12)
        malformed = MAGIC + nonce + AESGCM(self.session.lockout_lab_key()).encrypt(nonce, b'{"version":1,"nodes":{}}', MAGIC)
        self.store.path.write_bytes(malformed)
        with self.assertRaises(LabError):
            self.store.load()
        self.assertEqual(self.store.path.read_bytes(), malformed)
        self.store.path.unlink()
        model = self.store.load()
        add_node(model, "Prior map", "account")
        self.store.save(model)
        prior_raw = self.store.path.read_bytes()
        self.session.close()
        newer = vault.VaultSession()
        self.addCleanup(newer.close)
        newer.create("synthetic-different-master")
        with self.assertRaises(LabError):
            LabStore(newer).load()
        self.assertEqual(self.store.path.read_bytes(), prior_raw)

    def test_vault_backup_recovery_keeps_lab_key_when_salt_matches(self):
        model = self.store.load()
        add_node(model, "Recovery plan", "account")
        self.store.save(model)
        self.session.save([], [])  # creates an authenticated vault backup with the same salt
        self.session.close()
        self.file.write_bytes(b"synthetic corrupt primary")
        recovered = vault.VaultSession()
        self.addCleanup(recovered.close)
        recovered.recover_from_backup(MASTER, confirmed=True)
        self.assertEqual(LabStore(recovered).load(), model)

    def test_old_bare_list_vault_can_use_sidecar_without_format_change(self):
        self.session.close()
        from nasolt_vault import crypto
        import json
        salt = os.urandom(crypto.SALT_SIZE)
        key = crypto.derive_key(MASTER, salt)
        legacy = [{"id": "historical-synthetic", "title": "Old", "password": "synthetic-only"}]
        nonce, tag, cipher = crypto.encrypt_aes_gcm(json.dumps(legacy).encode(), key)
        self.file.write_bytes(crypto.MAGIC + bytes([crypto.FILE_VERSION]) + salt + nonce + tag + cipher)
        session = vault.VaultSession()
        self.addCleanup(session.close)
        entries, groups = session.open(MASTER)
        self.assertEqual((entries, groups), (legacy, []))
        store = LabStore(session)
        model = store.load()
        add_node(model, "Old account plan", "account")
        store.save(model)
        self.assertEqual(self.file.read_bytes(), crypto.MAGIC + bytes([crypto.FILE_VERSION]) + salt + nonce + tag + cipher)


if __name__ == "__main__":
    unittest.main()
