"""Synthetic installer transaction failures; no real installation or vault access."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
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

    def _populate_staged_copies(self):
        # Valid reserved copies can remain after an interrupted transaction.
        for name, staged in upgrade.STAGED.items():
            shutil.copyfile(self.candidates / upgrade.CANDIDATE[name],
                            self.install_dir / staged)

    def _interrupt_cleanup_at(self, journal, step, action):
        targets = [*(self.install_dir / name for name in upgrade.PREVIOUS.values()),
                   *(self.install_dir / name for name in upgrade.STAGED.values()),
                   self.install_dir / journal]
        real_unlink = Path.unlink
        deleted = 0

        def interrupted_unlink(path, *args, **kwargs):
            nonlocal deleted
            real_unlink(path, *args, **kwargs)
            if path in targets:
                deleted += 1
                if deleted == step:
                    raise KeyboardInterrupt("synthetic cleanup interruption")

        with mock.patch.object(Path, "unlink", new=interrupted_unlink):
            with self.assertRaises(KeyboardInterrupt):
                action()
        self.assertEqual(deleted, step)

    def test_clean_install_commits_after_registration(self):
        upgrade.install(self.install_dir, self.candidates)
        self.assertTrue((self.install_dir / upgrade.JOURNAL).is_file())
        with self.assertRaises(upgrade.UpgradeConflict):
            upgrade.finalize(self.install_dir)
        self.registry_lookup.return_value = str(self.install_dir)
        self.uninstall_lookup.return_value = str(self.install_dir / upgrade.UNINSTALL)
        upgrade.finalize(self.install_dir)
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

    def test_committed_upgrade_recovers_after_every_cleanup_step(self):
        for step in range(1, 7):  # two old copies, three staged copies, journal
            with self.subTest(step=step):
                if self.install_dir.exists():
                    shutil.rmtree(self.install_dir)
                self._owned_upgrade()
                sidecars = self._sidecars()
                upgrade.install(self.install_dir, self.candidates)
                self._populate_staged_copies()
                self._interrupt_cleanup_at(upgrade.COMMITTED_JOURNAL, step,
                                           lambda: upgrade.finalize(self.install_dir))
                self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())
                if step < 6:
                    self.assertTrue((self.install_dir / upgrade.COMMITTED_JOURNAL).exists())
                    with self.assertRaises(upgrade.UpgradeConflict):
                        upgrade.rollback(self.install_dir)
                if step % 2:
                    upgrade.finalize(self.install_dir)
                else:
                    upgrade.recover(self.install_dir)
                upgrade.finalize(self.install_dir)
                upgrade.recover(self.install_dir)  # idempotent retry
                self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(),
                                 b"synthetic-new-program")
                self.assertEqual((self.install_dir / upgrade.UNINSTALL).read_bytes(),
                                 b"synthetic-new-uninstaller")
                for name, content in sidecars.items():
                    self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)
                for name in (upgrade.JOURNAL, upgrade.COMMITTED_JOURNAL,
                             *upgrade.PREVIOUS.values(), *upgrade.STAGED.values()):
                    self.assertFalse((self.install_dir / name).exists())
                # The next upgrade is not blocked by an orphaned reserved file.
                upgrade.install(self.install_dir, self.candidates)
                upgrade.finalize(self.install_dir)

    def test_committed_clean_install_recovers_after_every_cleanup_step(self):
        for step in range(1, 5):  # three staged copies, journal
            with self.subTest(step=step):
                if self.install_dir.exists():
                    shutil.rmtree(self.install_dir)
                upgrade.install(self.install_dir, self.candidates)
                self.registry_lookup.return_value = str(self.install_dir)
                self.uninstall_lookup.return_value = str(self.install_dir / upgrade.UNINSTALL)
                self._populate_staged_copies()
                self._interrupt_cleanup_at(upgrade.COMMITTED_JOURNAL, step,
                                           lambda: upgrade.finalize(self.install_dir))
                if step % 2:
                    upgrade.finalize(self.install_dir)
                else:
                    upgrade.recover(self.install_dir)
                upgrade.finalize(self.install_dir)
                upgrade.recover(self.install_dir)
                self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(),
                                 b"synthetic-new-program")
                for name in (upgrade.JOURNAL, upgrade.COMMITTED_JOURNAL,
                             *upgrade.STAGED.values()):
                    self.assertFalse((self.install_dir / name).exists())
                upgrade.install(self.install_dir, self.candidates)

    def test_finalize_transition_is_atomic_for_recovery(self):
        for after_replace in (False, True):
            with self.subTest(after_replace=after_replace):
                if self.install_dir.exists():
                    shutil.rmtree(self.install_dir)
                self._owned_upgrade()
                sidecars = self._sidecars()
                upgrade.install(self.install_dir, self.candidates)
                real_replace = os.replace

                def interrupt_transition(source, target):
                    if Path(target).name == upgrade.COMMITTED_JOURNAL:
                        if after_replace:
                            real_replace(source, target)
                        raise KeyboardInterrupt("synthetic phase transition interruption")
                    return real_replace(source, target)

                with mock.patch.object(upgrade.os, "replace", side_effect=interrupt_transition):
                    with self.assertRaises(KeyboardInterrupt):
                        upgrade.finalize(self.install_dir)
                upgrade.recover(self.install_dir)
                expected = b"synthetic-new-program" if after_replace else b"synthetic-old-program"
                self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(), expected)
                for name, content in sidecars.items():
                    self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)
                self.assertFalse((self.install_dir / upgrade.JOURNAL).exists())
                self.assertFalse((self.install_dir / upgrade.COMMITTED_JOURNAL).exists())

    def test_setup_recovery_clears_each_journal_before_uninstall(self):
        programs = Path(self.temp.name) / "programs"
        desktop = Path(self.temp.name) / "desktop"
        programs.mkdir()
        desktop.mkdir()
        for state in ("pending", "committed", "restored"):
            with self.subTest(state=state):
                if self.install_dir.exists():
                    shutil.rmtree(self.install_dir)
                self._owned_upgrade()
                sidecars = self._sidecars()
                upgrade.install(self.install_dir, self.candidates)
                if state == "committed":
                    self._interrupt_cleanup_at(upgrade.COMMITTED_JOURNAL, 1,
                                               lambda: upgrade.finalize(self.install_dir))
                elif state == "restored":
                    self._interrupt_cleanup_at(upgrade.RESTORED_JOURNAL, 1,
                                               lambda: upgrade.rollback(self.install_dir))
                with self.assertRaises(ownership.ShortcutConflict):
                    ownership.manage("check-uninstall", self.install_dir, programs, desktop)
                with self.assertRaises(ownership.ShortcutConflict):
                    ownership.manage("uninstall", self.install_dir, programs, desktop)
                # NSIS runs recover before its ownership and uninstall checks.
                upgrade.recover(self.install_dir)
                ownership.manage("check-uninstall", self.install_dir, programs, desktop)
                ownership.manage("uninstall", self.install_dir, programs, desktop)
                for name, content in sidecars.items():
                    self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)
                self.assertFalse(any((self.install_dir / name).exists()
                                     for name in ownership.RECOVERY_JOURNALS))

    def test_restored_upgrade_recovers_after_every_cleanup_step(self):
        for step in range(1, 7):
            with self.subTest(step=step):
                if self.install_dir.exists():
                    shutil.rmtree(self.install_dir)
                self._owned_upgrade()
                sidecars = self._sidecars()
                upgrade.install(self.install_dir, self.candidates)
                real_replace = os.replace

                def interrupt_after_restored_journal(source, target):
                    real_replace(source, target)
                    if Path(target).name == upgrade.RESTORED_JOURNAL:
                        raise KeyboardInterrupt("synthetic phase transition interruption")

                with mock.patch.object(upgrade.os, "replace", side_effect=interrupt_after_restored_journal):
                    with self.assertRaises(KeyboardInterrupt):
                        upgrade.rollback(self.install_dir)
                self._populate_staged_copies()
                self._interrupt_cleanup_at(upgrade.RESTORED_JOURNAL, step,
                                           lambda: upgrade.recover(self.install_dir))
                if step < 6:
                    with self.assertRaises(upgrade.UpgradeConflict):
                        upgrade.finalize(self.install_dir)
                upgrade.recover(self.install_dir)
                upgrade.recover(self.install_dir)
                self.assertEqual((self.install_dir / upgrade.EXE).read_bytes(),
                                 b"synthetic-old-program")
                for name, content in sidecars.items():
                    self.assertEqual((self.install_dir / "data" / name).read_bytes(), content)
                for name in (upgrade.JOURNAL, upgrade.RESTORED_JOURNAL,
                             *upgrade.PREVIOUS.values(), *upgrade.STAGED.values()):
                    self.assertFalse((self.install_dir / name).exists())
                upgrade.install(self.install_dir, self.candidates)

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
