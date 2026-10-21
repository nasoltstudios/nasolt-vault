"""Synthetic Windows startup, tray, and activation regressions."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import tkinter
import types
import unittest
from pathlib import Path
from unittest import mock

from nasolt_vault.instance import InstanceCoordinator
from nasolt_vault.paths import APP_DIR, SOURCE_CHECKOUT
from nasolt_vault.windows_startup import (_launch_target, _legacy_launch_target,
                             _legacy_source_commands, _owned_shortcut, cleanup_legacy_voice_link,
                             launch_command, sync_cold_start_links, sync_startup)


def _make_test_shortcut(path: Path, target: str, arguments: str, workdir: str, icon: str) -> None:
    env = os.environ.copy()
    env.update({"NASOLT_LINK_PATH": str(path), "NASOLT_LINK_TARGET": target,
                "NASOLT_LINK_ARGS": arguments, "NASOLT_LINK_WORKDIR": workdir,
                "NASOLT_LINK_ICON": icon})
    script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:NASOLT_LINK_PATH); "
              "$s.TargetPath=$env:NASOLT_LINK_TARGET; $s.Arguments=$env:NASOLT_LINK_ARGS; "
              "$s.WorkingDirectory=$env:NASOLT_LINK_WORKDIR; "
              "$s.IconLocation=$env:NASOLT_LINK_ICON; $s.Hotkey='CTRL+ALT+V'; $s.Save()")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, capture_output=True, check=True, timeout=15)


class InstanceTests(unittest.TestCase):
    def test_duplicate_and_nonsecret_route_handoff(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_instance_") as folder:
            first = InstanceCoordinator(folder)
            second = InstanceCoordinator(folder)
            self.assertTrue(first.acquire())
            try:
                self.assertFalse(second.acquire())
                second.send("normal")
                self.assertEqual(first.drain_requests(), ["normal"])
                self.assertEqual(first.drain_requests(), [])
                self.assertLessEqual((Path(folder) / "app.instance.lock").stat().st_size, 1)
                with self.assertRaises(ValueError):
                    second.send("password")
                with self.assertRaises(ValueError):
                    second.send("voice")
            finally:
                second.close()
                first.close()
            self.assertTrue(second.acquire())
            second.close()

    def test_uninstaller_removes_startup_registration_and_links(self):
        source = (Path(__file__).resolve().parents[1] / "packaging" / "windows" / "NasoltVault.nsi").read_text(encoding="utf-8")
        uninstall = source.split('Section "Uninstall"', 1)[1]
        self.assertNotIn('DeleteRegValue HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "Nasolt Vault"', uninstall)
        self.assertIn('ExecWait \'"$INSTDIR\\${EXE}" --unregister-startup\'', uninstall)
        self.assertNotIn('Delete "$SMPROGRAMS\\${APPNAME}\\Nasolt VoiceKey.lnk"', uninstall)

    def test_obsolete_voice_command_does_not_launch_a_window(self):
        from nasolt_vault import main
        with mock.patch.object(main.sys, "argv", ["nasolt_vault", "--voice"]), \
             mock.patch.object(main, "cleanup_legacy_voice_link", return_value="isolated test mode") as cleanup, \
             mock.patch.object(main, "App", side_effect=AssertionError("GUI must stay closed")):
            self.assertEqual(main.main(), 0)
            cleanup.assert_called_once_with()


@unittest.skipUnless(sys.platform == "win32", "Windows startup integration")
class StartupRegistrationTests(unittest.TestCase):
    def test_per_user_run_value_enable_and_disable_without_real_registry(self):
        values = {}
        class Key:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
        def query(_key, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 1
        fake = types.SimpleNamespace(HKEY_CURRENT_USER=1, KEY_READ=1, KEY_WRITE=2, REG_SZ=1,
                                     CreateKeyEx=lambda *_args: Key(), QueryValueEx=query,
                                     SetValueEx=lambda _key, name, _reserved, _kind, value: values.__setitem__(name, value),
                                     DeleteValue=lambda _key, name: values.pop(name))
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            self.assertEqual(sync_startup(True, isolated=False), "enabled")
            self.assertIn("--background", values["Nasolt Vault"])
            self.assertEqual(sync_startup(False, isolated=False), "disabled")
            self.assertEqual(values, {})

            values["Nasolt Vault"] = '"C:\\Unrelated\\program.exe" --background'
            self.assertEqual(sync_startup(False, isolated=False), "unowned startup entry")
            self.assertEqual(values["Nasolt Vault"], '"C:\\Unrelated\\program.exe" --background')
            self.assertEqual(sync_startup(True, isolated=False), "unowned startup entry")
            self.assertEqual(values["Nasolt Vault"], '"C:\\Unrelated\\program.exe" --background')

            legacy = _legacy_source_commands()
            if legacy:
                values["Nasolt Vault"] = next(iter(legacy))
                self.assertEqual(sync_startup(True, isolated=False), "enabled")
                self.assertEqual(values["Nasolt Vault"], launch_command())

    def test_previous_source_venv_shortcut_is_recognized_only_for_this_checkout(self):
        if not SOURCE_CHECKOUT:
            self.skipTest("requires a source checkout")
        old_pythonw = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
        details = {"target": old_pythonw,
                   "arguments": subprocess.list2cmdline([os.path.join(APP_DIR, "main.py"), "--summon"]),
                   "workdir": APP_DIR, "icon": os.path.join(APP_DIR, "assets", "app.ico")}
        self.assertTrue(_owned_shortcut(details, "summon"))
        details["workdir"] = os.path.join(APP_DIR, "other")
        self.assertFalse(_owned_shortcut(details, "summon"))

    def test_isolated_data_never_changes_windows_startup(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_startup_") as folder:
            with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": folder}):
                self.assertEqual(sync_startup(True), "isolated test mode")
                self.assertEqual(sync_cold_start_links(True), "isolated test mode")

    def test_cold_start_links_created_and_removed_in_temporary_programs_dir(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_programs_") as folder:
            self.assertEqual(sync_cold_start_links(True, isolated=False, programs_dir=folder), "enabled")
            link_folder = Path(folder) / "Nasolt Vault"
            self.assertTrue((link_folder / "Nasolt Vault Summon.lnk").is_file())
            voice_link = link_folder / "Nasolt VoiceKey.lnk"
            self.assertFalse(voice_link.exists())
            target, arguments, workdir = _legacy_launch_target("voice") or _launch_target("voice")
            _make_test_shortcut(voice_link, target, arguments, workdir,
                                os.path.join(workdir, "assets", "app.ico"))
            self.assertTrue(voice_link.is_file())
            self.assertEqual(sync_cold_start_links(False, isolated=False, programs_dir=folder), "disabled")
            self.assertFalse(link_folder.exists())

    def test_unrelated_shortcut_with_legacy_name_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_programs_") as folder:
            link_folder = Path(folder) / "Nasolt Vault"
            link_folder.mkdir()
            link = link_folder / "Nasolt VoiceKey.lnk"
            _make_test_shortcut(link, os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                                  "System32", "notepad.exe"), "", folder, "")
            self.assertEqual(sync_cold_start_links(False, isolated=False, programs_dir=folder), "disabled")
            self.assertTrue(link.is_file())

    def test_similar_shortcut_in_another_folder_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_programs_") as folder:
            link_folder = Path(folder) / "Nasolt Vault"
            link_folder.mkdir()
            link = link_folder / "Nasolt Vault Summon.lnk"
            foreign = Path(folder) / "unrelated source"
            foreign.mkdir()
            target = str(Path(sys.executable).parent / "pythonw.exe")
            args = subprocess.list2cmdline([str(foreign / "main.py"), "--summon"])
            _make_test_shortcut(link, target, args, str(foreign),
                                str(foreign / "assets" / "app.ico"))
            self.assertEqual(sync_cold_start_links(False, isolated=False, programs_dir=folder), "disabled")
            self.assertTrue(link.is_file())

    def test_legacy_route_removes_only_its_owned_shortcut(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_programs_") as folder:
            link_folder = Path(folder) / "Nasolt Vault"
            link_folder.mkdir()
            voice_link = link_folder / "Nasolt VoiceKey.lnk"
            summon_link = link_folder / "Nasolt Vault Summon.lnk"
            for route, link in (("voice", voice_link), ("summon", summon_link)):
                target, arguments, workdir = _legacy_launch_target(route) or _launch_target(route)
                _make_test_shortcut(link, target, arguments, workdir,
                                    os.path.join(workdir, "assets", "app.ico"))
            self.assertEqual(cleanup_legacy_voice_link(isolated=False, programs_dir=folder), "removed")
            self.assertFalse(voice_link.exists())
            self.assertTrue(summon_link.is_file())

    def test_startup_command_requests_background_mode(self):
        self.assertIn("--background", launch_command())


@unittest.skipUnless(sys.platform == "win32", "Windows process integration")
class BackgroundProcessTests(unittest.TestCase):
    def test_actual_background_process_exits_and_restarts_with_synthetic_data(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        user32.FindWindowW.restype = wintypes.HWND
        user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.PostMessageW.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory(prefix="nasolt_process_") as folder:
            env = os.environ.copy()
            env["NASOLT_DATA_DIR"] = folder
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            # A Windows venv python.exe may be a redirector with a different
            # PID than the interpreter that owns the native tray window.
            marker = Path(folder, "test-process-id")
            launcher = Path(folder, "launch-synthetic.py")
            launcher.write_text(
                "import os, runpy, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['NASOLT_TEST_PID_FILE']).write_text(str(os.getpid()))\n"
                "sys.argv = ['nasolt_vault', '--background']\n"
                "runpy.run_module('nasolt_vault', run_name='__main__')\n",
                encoding="utf-8")
            env["NASOLT_TEST_PID_FILE"] = str(marker)
            for _ in range(2):
                marker.unlink(missing_ok=True)
                process = subprocess.Popen([sys.executable, str(launcher)], env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline = time.monotonic() + 12
                    hwnd = None
                    while time.monotonic() < deadline:
                        if marker.is_file():
                            hwnd = user32.FindWindowW(f"NasoltVaultTray_{marker.read_text()}", None)
                        if hwnd or process.poll() is not None:
                            break
                        time.sleep(0.05)
                    self.assertTrue(hwnd, "Background process did not create a tray window")
                    second = subprocess.run([sys.executable, "-m", "nasolt_vault", "--background"], env=env,
                                            capture_output=True, timeout=8,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
                    self.assertEqual(second.returncode, 0)
                    self.assertIsNone(process.poll(), "Second launch terminated the first process")
                    self.assertTrue(user32.PostMessageW(hwnd, 0x0111, 4, 0))  # Tray Exit action.
                    _out, err = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 0, err.decode(errors="replace"))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)


@unittest.skipUnless(sys.platform == "win32", "Windows GUI integration")
class BackgroundGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_background_")
        self.env = mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": self.temp.name})
        self.env.start()
        from nasolt_vault import vault
        self.paths = mock.patch.multiple(vault, VAULT_DIR=self.temp.name,
                                         VAULT_FILE=str(Path(self.temp.name) / "vault.enc"))
        self.paths.start()
        from nasolt_vault.main import App
        self.app = App(background=True)
        deadline = time.monotonic() + 10
        while not self.app.tray.active and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)

    def tearDown(self):
        try:
            exists = self.app.winfo_exists()
        except tkinter.TclError:
            exists = False
        if exists:
            self.app.close()
        self.paths.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_background_starts_hidden_locked_then_open_close_and_reopen(self):
        self.app.update()
        self.assertTrue(self.app.tray.active, f"{self.app.tray.last_error}; phase={self.app.tray.phase}; thread={self.app.tray._thread}; "
                        f"alive={self.app.tray._thread.is_alive() if self.app.tray._thread else None}; "
                        f"exists={self.app.winfo_exists()}")
        self.assertEqual(self.app.state(), "withdrawn",
                         f"tray={self.app.tray.active}, phase={self.app.tray.phase}, error={self.app.tray.last_error}")
        self.assertFalse(self.app.session.is_open)
        self.app.tray_action("open")
        self.app.update()
        self.assertEqual(self.app.state(), "normal")
        self.app.session.create("Synthetic-only-master-42!")
        self.app.on_unlocked([], [])
        self.assertTrue(self.app.session.is_open)
        self.app.on_window_close()
        self.app.update()
        self.assertEqual(self.app.state(), "withdrawn")
        self.assertFalse(self.app.session.is_open)
        self.assertIsNone(self.app.quick_access.request)
        self.app.tray_action("open")
        self.assertEqual(self.app.login.mode, "unlock")
        self.app.session.open("Synthetic-only-master-42!")
        self.app.on_unlocked([], [])
        self.assertTrue(self.app.session.is_open)
        self.app.tray_action("exit")
        self.assertFalse(self.app.tray.active)
        from nasolt_vault.main import App
        self.app = App(background=True)
        self.assertFalse(self.app.session.is_open)
        self.assertEqual(self.app.login.mode, "unlock")
        self.assertEqual(self.app.state(), "withdrawn")

    def test_tray_settings_requires_normal_auth_when_locked(self):
        self.app.session.create("Synthetic-only-master-42!")
        self.app.on_unlocked([], [])
        self.app.on_window_close()
        self.app.tray_action("settings")
        self.assertIsNotNone(self.app.quick_access.request)
        self.assertTrue(self.app.quick_access.request.await_login)
        self.assertEqual(self.app.quick_access.request.destination, "settings")
        self.assertEqual(self.app.state(), "withdrawn")
        self.assertTrue(self.app.quick_access.reauth_prompt.winfo_viewable())
        self.app.quick_access.cancel_request()
        self.assertIsNone(self.app.quick_access.request)

    def test_cold_start_summon_route_stays_hidden_until_authentication(self):
        from nasolt_vault import vault
        from nasolt_vault.main import App
        self.app.close()
        session = vault.VaultSession()
        try:
            session.create("Synthetic-only-master-42!")
        finally:
            session.close()
        self.app = App(initial_route="normal", background=True)
        # Background startup allows the tray up to ten seconds before revealing
        # the main window; give this integration check the same window plus slack.
        deadline = time.monotonic() + 12
        while (not self.app.tray.active or self.app.quick_access.reauth_prompt is None) and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertIsNotNone(self.app.quick_access.reauth_prompt)
        self.assertTrue(self.app.quick_access.reauth_prompt.winfo_viewable())
        self.assertTrue(self.app.tray.active,
                        f"phase={self.app.tray.phase}, error={self.app.tray.last_error}")
        self.assertEqual(self.app.state(), "withdrawn",
                         f"tray={self.app.tray.active}, phase={self.app.tray.phase}")
        self.assertFalse(self.app.session.is_open)
        self.app.quick_access.reauth_prompt.password.set("Synthetic-only-master-42!")
        self.app.quick_access.reauth_prompt.submit()
        deadline = time.monotonic() + 6
        while self.app.quick_access.summon_popup is None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertIsNotNone(self.app.quick_access.summon_popup)
        self.assertEqual(self.app.state(), "withdrawn")
