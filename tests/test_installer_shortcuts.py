"""Installer ownership tests use only synthetic links in temporary folders."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nasolt_vault import installer_shortcuts as shortcuts


class ShortcutOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_installer_links_")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.install = root / "installed"
        self.programs = root / "programs"
        self.desktop = root / "desktop"
        self.install.mkdir()
        self.programs.mkdir()
        self.desktop.mkdir()
        (self.install / "installed.flag").write_text("synthetic installer marker", encoding="utf-8")
        self.registry = mock.patch.object(shortcuts, "_registered_install_dir", return_value=str(self.install))
        self.registry.start()
        self.addCleanup(self.registry.stop)

    def _link(self, name="main"):
        return shortcuts._links(self.install, self.programs, self.desktop)[name]

    def _details(self, target, *, arguments="", workdir="", icon="", hotkey=""):
        return {"target": str(target), "arguments": arguments, "workdir": workdir,
                "icon": icon, "hotkey": hotkey}

    def test_legacy_upgrade_accepts_original_target_and_default_attributes(self):
        link, target = self._link()
        link.parent.mkdir()
        link.write_text("synthetic legacy shortcut")
        with mock.patch.object(shortcuts, "_link_details", return_value=self._details(target)):
            shortcuts.manage("check-main", self.install, self.programs, self.desktop)
            with mock.patch.object(shortcuts, "_create") as create:
                shortcuts.manage("install-main", self.install, self.programs, self.desktop)
                create.assert_called_once()  # only missing uninstall link
        self.assertEqual(link.read_text(), "synthetic legacy shortcut")

    def test_foreign_and_ambiguous_links_block_upgrade_without_replacement(self):
        link, target = self._link()
        link.parent.mkdir()
        link.write_text("foreign shortcut")
        variants = (
            self._details(self.install / "foreign.exe"),
            self._details(target, arguments="--unexpected"),
            self._details(target, workdir=str(self.programs)),
            self._details(target, icon=str(self.programs / "foreign.ico")),
            self._details(target, hotkey="CTRL+ALT+N"),
            None,
        )
        for details in variants:
            with self.subTest(details=details), mock.patch.object(shortcuts, "_link_details", return_value=details), \
                 mock.patch.object(shortcuts, "_create") as create:
                with self.assertRaises(shortcuts.ShortcutConflict):
                    shortcuts.manage("install-main", self.install, self.programs, self.desktop)
                create.assert_not_called()
                self.assertEqual(link.read_text(), "foreign shortcut")

    def test_same_target_without_installer_registration_is_not_owned(self):
        link, target = self._link()
        link.parent.mkdir()
        link.write_text("unregistered shortcut")
        with mock.patch.object(shortcuts, "_registered_install_dir", return_value=None), \
             mock.patch.object(shortcuts, "_link_details", return_value=self._details(target)):
            with self.assertRaises(shortcuts.ShortcutConflict):
                shortcuts.manage("check-main", self.install, self.programs, self.desktop)

    def test_uninstall_refuses_all_shortcut_deletion_if_one_is_foreign(self):
        main, main_target = self._link()
        remove, remove_target = self._link("uninstall")
        main.parent.mkdir()
        main.write_text("owned")
        remove.write_text("foreign")
        def details(link):
            return self._details(main_target if link == main else self.programs / "foreign.exe")
        with mock.patch.object(shortcuts, "_link_details", side_effect=details):
            with self.assertRaises(shortcuts.ShortcutConflict):
                shortcuts.manage("uninstall", self.install, self.programs, self.desktop)
        self.assertTrue(main.exists())
        self.assertTrue(remove.exists())

    def test_uninstall_preserves_other_start_menu_content(self):
        main, main_target = self._link()
        remove, remove_target = self._link("uninstall")
        main.parent.mkdir()
        for link in (main, remove):
            link.write_text("synthetic shortcut")
        other = main.parent / "Personal shortcut.lnk"
        other.write_text("unrelated item")
        def details(link):
            return self._details(main_target if link == main else remove_target)
        with mock.patch.object(shortcuts, "_link_details", side_effect=details):
            shortcuts.manage("uninstall", self.install, self.programs, self.desktop)
        self.assertFalse(main.exists())
        self.assertFalse(remove.exists())
        self.assertTrue(other.exists())
        self.assertTrue(main.parent.is_dir())

    def test_desktop_conflict_does_not_modify_foreign_link(self):
        link, _ = self._link("desktop")
        link.write_text("personal desktop shortcut")
        with mock.patch.object(shortcuts, "_link_details", return_value=None), \
             mock.patch.object(shortcuts, "_create") as create:
            with self.assertRaises(shortcuts.ShortcutConflict):
                shortcuts.manage("install-desktop", self.install, self.programs, self.desktop)
            create.assert_not_called()
        self.assertEqual(link.read_text(), "personal desktop shortcut")

    def test_nsi_checks_ownership_before_copy_and_uninstall_deletion(self):
        source = (Path(__file__).resolve().parents[1] / "packaging" / "windows" / "NasoltVault.nsi").read_text(encoding="utf-8")
        install = source.split('Section "${APPNAME} (required)" SecMain', 1)[1].split("SectionEnd", 1)[0]
        uninstall = source.split('Section "Uninstall"', 1)[1]
        self.assertLess(install.index("--installer-shortcuts check-main"), install.index('File "installed.flag"'))
        self.assertLess(uninstall.index("--installer-shortcuts uninstall"), uninstall.index('Delete "$INSTDIR\\${EXE}"'))
        self.assertNotIn("CreateShortcut", source)
        self.assertNotIn('Delete "$DESKTOP\\${APPNAME}.lnk"', source)


@unittest.skipUnless(sys.platform == "win32", "Windows Shell shortcut integration")
class WindowsShortcutIntegrationTests(unittest.TestCase):
    def test_real_shell_link_creation_upgrade_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_shell_links_") as folder:
            root = Path(folder)
            install, programs, desktop = root / "installed", root / "programs", root / "desktop"
            for path in (install, programs, desktop):
                path.mkdir()
            (install / "installed.flag").write_text("synthetic installer marker", encoding="utf-8")
            with mock.patch.object(shortcuts, "_registered_install_dir", return_value=str(install)):
                shortcuts.manage("install-main", install, programs, desktop)
                main, main_target = shortcuts._links(install, programs, desktop)["main"]
                self.assertTrue(main.is_file())
                self.assertTrue(shortcuts._owned(shortcuts._link_details(main), main_target, install))
                shortcuts.manage("install-main", install, programs, desktop)
                shortcuts.manage("uninstall", install, programs, desktop)
                self.assertFalse(main.exists())
