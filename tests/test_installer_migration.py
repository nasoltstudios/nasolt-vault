"""Installer migration checks with disposable, synthetic ciphertext only."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import installer_migration as migration
from crypto import build_vault_blob, derive_key, encrypt_aes_gcm


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="migration_", dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "portable"
        self.target = root / "installed"
        self.source.mkdir()
        salt = b"s" * 32
        key = derive_key("synthetic migration master", salt)
        nonce, tag, ciphertext = encrypt_aes_gcm(b'{"entries":[],"groups":[]}', key)
        self.synthetic_blob = build_vault_blob(salt, nonce, tag, ciphertext)
        (self.source / "vault.enc").write_bytes(self.synthetic_blob)

    def test_verified_copy_preserves_source(self):
        result = migration.migrate_vault(self.source, self.target)
        self.assertEqual(result.read_bytes(), self.synthetic_blob)
        self.assertEqual((self.source / "vault.enc").read_bytes(), self.synthetic_blob)
        self.assertEqual(list(self.target.glob("*.tmp")), [])

    def test_missing_and_invalid_source(self):
        (self.source / "vault.enc").unlink()
        with self.assertRaises(migration.MigrationError) as error:
            migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.SOURCE_INVALID)
        (self.source / "vault.enc").write_bytes(b"invalid")
        with self.assertRaises(migration.MigrationError) as error:
            migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.SOURCE_INVALID)
        self.assertFalse((self.target / "vault.enc").exists())

    def test_existing_destination_is_never_replaced(self):
        self.target.mkdir()
        (self.target / "vault.enc").write_bytes(b"existing")
        with self.assertRaises(migration.MigrationError) as error:
            migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.DESTINATION_EXISTS)
        self.assertEqual((self.target / "vault.enc").read_bytes(), b"existing")

    def test_same_source_and_destination(self):
        with self.assertRaises(migration.MigrationError) as error:
            migration.migrate_vault(self.source, self.source)
        self.assertEqual(error.exception.code, migration.DESTINATION_EXISTS)

    def test_copy_failure_cleans_stage_and_preserves_source(self):
        with patch.object(migration.os, "fsync", side_effect=OSError("synthetic failure")):
            with self.assertRaises(migration.MigrationError) as error:
                migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.COPY_FAILED)
        self.assertFalse((self.target / "vault.enc").exists())
        self.assertEqual(list(self.target.glob(".nasolt-migration-*")), [])
        self.assertEqual((self.source / "vault.enc").read_bytes(), self.synthetic_blob)

    def test_publish_failure_leaves_original_and_no_destination(self):
        operation = "rename" if os.name == "nt" else "link"
        with patch.object(migration.os, operation, side_effect=OSError("synthetic interruption")):
            with self.assertRaises(migration.MigrationError) as error:
                migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.COPY_FAILED)
        self.assertFalse((self.target / "vault.enc").exists())
        self.assertEqual(list(self.target.glob(".nasolt-migration-*")), [])
        self.assertEqual((self.source / "vault.enc").read_bytes(), self.synthetic_blob)

    @unittest.skipUnless(os.name == "nt", "Windows byte-range lock")
    def test_locked_source_is_refused(self):
        import msvcrt

        lock_path = self.source / "vault.enc.lock"
        lock_path.write_bytes(b"0")
        with lock_path.open("r+b") as holder:
            msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with self.assertRaises(migration.MigrationError) as error:
                    migration.migrate_vault(self.source, self.target)
                self.assertEqual(error.exception.code, migration.SOURCE_BUSY)
                self.assertFalse((self.target / "vault.enc").exists())
            finally:
                holder.seek(0)
                msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)

    def test_changed_source_does_not_publish(self):
        digest = migration._digest_file
        calls = 0

        def changing_digest(path):
            nonlocal calls
            calls += 1
            if calls == 3:
                (self.source / "vault.enc").write_bytes(self.synthetic_blob + b"changed")
            return digest(path)

        with patch.object(migration, "_digest_file", side_effect=changing_digest):
            with self.assertRaises(migration.MigrationError) as error:
                migration.migrate_vault(self.source, self.target)
        self.assertEqual(error.exception.code, migration.SOURCE_CHANGED)
        self.assertFalse((self.target / "vault.enc").exists())

    def test_linked_source_is_rejected(self):
        linked = Path(self.temporary.name) / "linked"
        try:
            linked.symlink_to(self.source, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(migration.MigrationError) as error:
            migration.migrate_vault(linked, self.target)
        self.assertEqual(error.exception.code, migration.UNSAFE_PATH)

    def test_optional_settings_copy_and_conflict(self):
        (self.source / "settings.json").write_bytes(b'{"theme":"Dark"}')
        (self.source / "vault.enc.bak").write_bytes(b"synthetic encrypted backup")
        (self.source / "lockout_lab.enc").write_bytes(b"synthetic encrypted sidecar")
        (self.source / "lockout_lab.enc.bak").write_bytes(b"synthetic encrypted sidecar backup")
        migration.migrate_vault(self.source, self.target)
        migration.migrate_settings(self.source, self.target)
        for name in ("vault.enc.bak", "lockout_lab.enc", "lockout_lab.enc.bak"):
            migration._migrate_optional_file(self.source, self.target, name)
            self.assertEqual((self.target / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual((self.target / "settings.json").read_bytes(), b'{"theme":"Dark"}')
        (self.source / "settings.json").write_bytes(b'{"theme":"Light"}')
        migration.migrate_settings(self.source, self.target)
        self.assertEqual((self.target / "settings.json").read_bytes(), b'{"theme":"Dark"}')
        (self.source / "lockout_lab.enc").write_bytes(b"new synthetic sidecar")
        with self.assertRaises(migration.MigrationError) as error:
            migration._migrate_optional_file(self.source, self.target, "lockout_lab.enc")
        self.assertEqual(error.exception.code, migration.SETTINGS_FAILED)
        self.assertEqual((self.target / "lockout_lab.enc").read_bytes(), b"synthetic encrypted sidecar")

    def test_settings_failure_reports_partial_result(self):
        (self.source / "settings.json").write_bytes(b"settings")
        old_appdata = os.environ.get("APPDATA")
        try:
            os.environ["APPDATA"] = self.temporary.name
            with patch.object(migration, "migrate_settings", side_effect=migration.MigrationError(migration.UNSAFE_PATH, "synthetic")):
                self.assertEqual(migration.cli(str(self.source)), migration.SETTINGS_FAILED if os.name == "nt" else migration.BAD_ARGUMENTS)
            if os.name == "nt":
                self.assertEqual(migration.installed_data_dir().joinpath("vault.enc").read_bytes(), self.synthetic_blob)
        finally:
            if old_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old_appdata

    def test_uninstaller_contains_no_recursive_user_data_delete(self):
        script = (Path(__file__).parent.parent / "packaging" / "windows" / "NasoltVault.nsi").read_text(encoding="utf-8")
        self.assertNotIn("RMDir /r", script)
        self.assertNotIn("CopyFiles /SILENT", script)
        self.assertIn("--migrate-vault", script)
        self.assertIn("IfErrors migrate_launch_failed", script)


if __name__ == "__main__":
    unittest.main()
