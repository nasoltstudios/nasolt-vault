"""Synthetic installer transaction failures; no real installation or vault access."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nasolt_vault import installer_shortcuts as ownership
from nasolt_vault import installer_upgrade as upgrade


class InstallerUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_upgrade_", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.install_dir = root / "installed"
        self.candidates = root / "candidate"
        self.candidates.mkdir()
        (self.candidates / upgrade.CANDIDATE[upgrade.EXE]).write_bytes(b"synthetic-new-program")
        (self.candidates / upgrade.CANDIDATE[upgrade.UNINSTALL]).write_bytes(b"synthetic-new-uninstaller")
        marker = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "installed.flag"
        (self.candidates / upgrade.MARKER).write_bytes(marker.read_bytes())
        self.registered = mock.patch.object(ownership, "_registered_install_dir", return_value=None)
        self.uninstaller = mock.patch.object(ownership, "_registered_uninstaller", return_value=None)
        self.registry_lookup = self.registered.start()
        self.uninstall_lookup = self.uninstaller.start()
        self.addCleanup(self.uninstaller.stop)
        self.addCleanup(self.registered.stop)

    def _owned_upgrade(self):
        self.install_dir.mkdir()
        (self.install_dir / upgrade.EXE).write_bytes(b"synthetic-old-program")
        (self.install_dir / upgrade.UNINSTALL).write_bytes(b"synthetic-old-uninstaller")
        (self.install_dir / upgrade.MARKER).write_bytes(b"synthetic-older-install-marker")
        self.registry_lookup.return_value = str(self.install_dir)
        self.uninstall_lookup.return_value = '"' + str(self.install_dir / upgrade.UNINSTALL) + '"'

    def _sidecars(self):
        data = self.install_dir / "data"
        data.mkdir()
        files = {"vault.enc": b"fictional-encrypted-vault",
                 "vault.enc.bak": b"fictional-encrypted-backup",
                 "lockout_lab.enc": b"fictional-encrypted-sidecar",
                 "settings.json": b'{"synthetic": true}'}
        for name, content in files.items():
            (data / name).write_bytes(content)
        return files

    def test_clean_install_commits_after_registration(self):
        upgrade.install(self.install_dir, self.candidates)
        self.assertTrue((self.install_dir / upgrade.JOURNAL).is_file())
        with self.assertRaises(upgrade.UpgradeConflict):
            upgrade.finalize(self.install_dir)
        self.registry_lookup.return_value = str(self.install_dir)
        self.uninstall_lookup.return_value = str(self.install_dir / upgrade.UNINSTALL)
        upgrade.finalize(self.install_dir)
        self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(), b"synthetic-new-program")
        self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())

    def test_upgrade_interruption_restores_previous_program_and_preserves_data(self):
        self._owned_upgrade()
        sidecars = self._sidecars()
        real_replace = os.replace

        def interrupt_after_exe(source, target):
            real_replace(source, target)
            if Path(target).name == upgrade.EXE:
                raise KeyboardInterrupt("synthetic process termination")

        with mock.patch.object(upgrade.os, "replace", side_effect=interrupt_after_exe):
            with self.assertRaises(KeyboardInterrupt):
                upgrade.install(self.install_dir, self.candidates)
        self.assertTrue((self.install_dir / upgrade.JOURNAL).exists())
        upgrade.recover(self.install_dir)
        self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(), b"synthetic-old-program")
        self.assertEqual((self.install_dir / upgrade.UNINSTALL).read_bytes(), b"synthetic-old-uninstaller")
        self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())
        for name, content in sidecars.items():
            self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)

    def test_upgrade_commits_with_an_older_marker_and_preserves_data(self):
        self._owned_upgrade()
        sidecars = self._sidecars()
        upgrade.install(self.install_dir, self.candidates)
        upgrade.finalize(self.install_dir)
        self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(), b"synthetic-new-program")
        self.assertEqual((self.install_dir / upgrade.MARKER).read_bytes(), b"synthetic-older-install-marker")
        self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())
        self.assertFalse((self.install_dir / upgrade.PREVIOUS[upgrade.EXE]).exists())
        for name, content in sidecars.items():
            self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)

    def test_denied_uninstaller_replace_rolls_back_upgrade(self):
        self._owned_upgrade()
        real_replace = os.replace

        def deny_uninstaller(source, target):
            if Path(target).name == upgrade.UNINSTALL and Path(source).name == upgrade.STAGED[upgrade.UNINSTALL]:
                raise PermissionError("synthetic denied write")
            return real_replace(source, target)

        with mock.patch.object(upgrade.os, "replace", side_effect=deny_uninstaller):
            with self.assertRaises(PermissionError):
                upgrade.install(self.install_dir, self.candidates)
        self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(), b"synthetic-old-program")
        self.assertEqual((self.install_dir / upgrade.UNINSTALL).read_bytes(), b"synthetic-old-uninstaller")
        self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())

    def test_new_install_interruption_removes_only_transaction_files(self):
        self.install_dir.mkdir()
        real_rename = os.rename

        def interrupt_after_exe(source, target):
            real_rename(source, target)
            if Path(target).name == upgrade.EXE:
                raise KeyboardInterrupt("synthetic process termination")

        with mock.patch.object(upgrade.os, "rename", side_effect=interrupt_after_exe):
            with self.assertRaises(KeyboardInterrupt):
                upgrade.install(self.install_dir, self.candidates)
        (self.install_dir / "personal-data.txt").write_bytes(b"preserve unrelated files")
        upgrade.recover(self.install_dir)
        self.assertEqual((self.install_dir / "personal-data.txt").read_bytes(), b"preserve unrelated files")
        for name in (upgrade.EXE, upgrade.UNINSTALL, upgrade.MARKER, upgrade.JOURNAL):
            self.assertFalse((self.install_dir / name).exists())

    def test_foreign_folder_and_tampered_journal_refuse_changes(self):
        self.install_dir.mkdir()
        (self.install_dir / "personal-data.txt").write_bytes(b"preserve unrelated files")
        with self.assertRaises(upgrade.UpgradeConflict):
            upgrade.install(self.install_dir, self.candidates)
        self.assertEqual((self.install_dir / "personal-data.txt").read_bytes(), b"preserve unrelated files")
        (self.install_dir / upgrade.JOURNAL).write_text('{"version": 1, "kind": "upgrade"}', encoding="utf-8")
        with self.assertRaises(upgrade.UpgradeConflict):
            upgrade.recover(self.install_dir)
        self.assertEqual((self.install_dir / "personal-data.txt").read_bytes(), b"preserve unrelated files")


if __name__ == "__main__":
    unittest.main()
