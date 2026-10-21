"""Synthetic-only quick access regression checks."""
from __future__ import annotations

import os
import json
import sys
import tempfile
import threading
import time
import tkinter
import unittest
from pathlib import Path
from unittest import mock

import quick_access
import app_settings
import hello_enrollment
from windows_shortcuts import SHORTCUTS, WindowsHotkeys


class ShortcutAndSearchTests(unittest.TestCase):
    def test_only_summon_shortcuts_remain(self):
        self.assertEqual(app_settings.DEFAULTS["summon_shortcut"], "ctrl+alt+n")
        self.assertNotIn("voicekey_shortcut", app_settings.DEFAULTS)
        self.assertTrue(app_settings.DEFAULTS["start_with_windows"])
        self.assertNotIn("ctrl+alt+v", SHORTCUTS)
        self.assertTrue(all(not key.endswith("+v") for key in SHORTCUTS))

    def test_legacy_voice_preference_is_ignored_and_removed_on_next_save(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_legacy_settings_", dir=Path(__file__).parent) as folder:
            with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": folder}):
                settings = Path(folder) / "settings.json"
                settings.write_text(json.dumps({"voicekey_shortcut": "ctrl+alt+v",
                                                "summon_shortcut": "ctrl+alt+n",
                                                "autolock_minutes": 5}), encoding="utf-8")
                loaded = app_settings.load_settings()
                self.assertNotIn("voicekey_shortcut", loaded)
                self.assertEqual(loaded["autolock_minutes"], 5)
                app_settings.set_value("summon_timeout_seconds", 60)
                saved = json.loads(settings.read_text(encoding="utf-8"))
                self.assertNotIn("voicekey_shortcut", saved)
                self.assertEqual(saved["autolock_minutes"], 5)

    def test_search_does_not_expose_passwords_or_notes(self):
        entries = [{"id": "synthetic", "title": "Example Bank", "username": "fictional-user",
                    "url": "example.invalid", "password": "SyntheticSecret!", "notes": "hidden marker"}]
        result = quick_access.find_accounts(entries, "example fictional")
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]), {"id", "title", "username", "url"})
        self.assertEqual(quick_access.find_accounts(entries, "SyntheticSecret"), [])
        self.assertEqual(quick_access.find_accounts(entries, "hidden marker"), [])
        self.assertEqual(quick_access.find_accounts([], ""), [])


@unittest.skipUnless(sys.platform == "win32", "Windows GUI checks")
class QuickAccessGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_quick_", dir=Path(__file__).parent)
        self.env = mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": self.temp.name})
        self.env.start()
        import vault
        from main import App
        self.paths = mock.patch.multiple(vault, VAULT_DIR=self.temp.name,
                                         VAULT_FILE=str(Path(self.temp.name) / "vault.enc"))
        self.paths.start()
        self.app = App()
        self.app.session.create("Synthetic-only-master-42!")
        self.app.on_unlocked([], [])
        self.app.update()
        self.entry = vault._default_entry(title="Example Bank", username="fictional-user",
                                          password="SyntheticSecret!", url="example.invalid")
        self.assertTrue(self.app.shell.add_entry(dict(self.entry)))

    def tearDown(self):
        try:
            if self.app.winfo_exists():
                self.app.close()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    self.app.update()
                except tkinter.TclError:
                    break
                if not self.app.winfo_exists():
                    break
                time.sleep(0.02)
        except tkinter.TclError:
            pass
        self.paths.stop()
        self.env.stop()
        self.temp.cleanup()

    def authenticate_summon(self):
        qa = self.app.quick_access
        request_id = qa.request_normal()
        self.assertIsNotNone(qa.reauth_prompt)
        self.assertIsNone(qa.summon_popup)
        qa.reauth_prompt.password.set("Synthetic-only-master-42!")
        qa.reauth_prompt.submit()
        deadline = time.monotonic() + 5
        while qa.summon_popup is None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertIsNotNone(qa.summon_popup)
        self.assertEqual(qa.request.ident, request_id)
        return qa

    def test_popup_search_copy_and_lock_revoke(self):
        qa = self.authenticate_summon()
        self.app.update()
        popup = qa.summon_popup
        self.assertTrue(popup.winfo_viewable())
        self.assertIs(popup, qa.summon_popup)
        self.assertTrue(qa.open_summon())
        self.assertIs(popup, qa.summon_popup)
        self.assertNotIn("SyntheticSecret!", str(popup.winfo_children()))
        popup.query.insert(0, "Example")
        popup._refresh()
        self.assertEqual(len(popup._rows), 1)
        popup._select(0)
        with mock.patch.object(quick_access.clipboard, "copy_to_clipboard", return_value=True) as copy:
            popup._copy_selected("username")
            copy.assert_called_once_with("fictional-user")
            popup._copy_selected("password")
            self.assertEqual(copy.call_args.args, ("SyntheticSecret!",))
        self.assertIsNone(qa.summon_popup)
        self.assertFalse(popup.winfo_exists())

        self.authenticate_summon()
        prior_epoch = qa._epoch
        self.app.shell.lock()
        self.app.update()
        self.assertIsNone(qa.summon_popup)
        self.assertFalse(self.app.session.is_open)
        with mock.patch.object(quick_access.clipboard, "copy_to_clipboard") as copy:
            self.assertFalse(qa.copy_field(self.entry["id"], "password", prior_epoch))
            copy.assert_not_called()
        self.assertFalse(qa.open_summon())
        self.assertIsNotNone(self.app.login)

    def test_autolock_closes_popup_and_stale_event_ignored(self):
        qa = self.app.quick_access
        qa = self.authenticate_summon()
        qa.hotkeys.events.put((time.monotonic() - 10, "summon"))
        self.app.last_activity = time.monotonic() - 1200
        self.app._last_wall = time.time() - 1200
        self.app.shell._tick()
        self.app.update()
        self.assertIsNone(qa.summon_popup)
        self.assertIsNone(self.app.shell)
        with mock.patch.object(quick_access, "active_desktop_available", return_value=True):
            qa._poll()
        self.assertIsNone(qa.summon_popup)

    def test_removed_voice_event_cannot_open_quick_access(self):
        qa = self.app.quick_access
        self.assertFalse(hasattr(qa, "request_voice"))
        self.assertFalse(hasattr(qa, "voice_popup"))
        with mock.patch.object(quick_access, "active_desktop_available", return_value=True):
            qa.hotkeys.events.put((time.monotonic(), "voice"))
            qa._poll()
        self.assertIsNone(qa.request)
        self.assertIsNone(qa.summon_popup)
        self.assertTrue(self.app.session.is_open)

    def test_wrong_password_and_cancel_never_grant_access(self):
        qa = self.app.quick_access
        qa.request_normal()
        qa.reauth_prompt.password.set("Wrong synthetic password")
        qa.reauth_prompt.submit()
        deadline = time.monotonic() + 5
        while qa.request is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertIsNone(qa.request)
        self.assertIsNone(qa.summon_popup)
        self.assertFalse(qa.open_summon())
        qa.request_normal()
        qa.cancel_request()
        self.assertIsNone(qa.request)
        self.assertFalse(qa.open_summon())

    def test_stale_auth_result_after_lock_is_ignored(self):
        qa = self.app.quick_access
        ident = qa.request_normal()
        epoch = qa._epoch
        self.app.shell.lock()
        qa._auth_results.put((ident, epoch, "verified", True))
        qa._process_auth_results()
        self.assertFalse(self.app.session.is_open)
        self.assertIsNone(qa.summon_popup)

    def test_cancel_locked_auth_while_worker_is_decrypting(self):
        import vault
        self.app.shell.lock()
        qa = self.app.quick_access
        ident = qa.request_normal()
        entered, release = threading.Event(), threading.Event()
        original = vault._read_valid

        def delayed(*args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("synthetic unlock gate timed out")
            return original(*args)

        with mock.patch.object(vault, "_read_valid", side_effect=delayed):
            qa._verify_async(ident, "Synthetic-only-master-42!")
            self.assertTrue(entered.wait(5))
            timer = threading.Timer(0.1, release.set)
            timer.start()
            try:
                qa.cancel_request(ident)
            finally:
                release.set()
                timer.join(5)
            qa._auth_worker.join(5)
        qa._process_auth_results()
        self.assertFalse(self.app.session.is_open)
        self.assertIsNone(self.app.shell)
        self.assertIsNone(qa.request)

    def test_changed_vault_file_revokes_summon_access(self):
        import vault
        qa = self.authenticate_summon()
        vault_path = Path(self.temp.name) / "vault.enc"
        with vault_path.open("ab") as changed:
            changed.write(b"synthetic-tamper")
        with mock.patch.object(quick_access.clipboard, "copy_to_clipboard") as copy:
            self.assertEqual(qa.search("Example"), [])
            self.assertFalse(qa.copy_field(self.entry["id"], "password"))
            copy.assert_not_called()
        self.assertFalse(qa.open_summon())

    def test_hidden_locked_shortcut_uses_visible_popup_and_keeps_main_hidden(self):
        self.app.on_window_close()
        self.app.update()
        self.assertEqual(self.app.state(), "withdrawn")
        qa = self.app.quick_access
        qa.request_normal()
        self.app.update()
        self.assertTrue(qa.request.await_login)
        self.assertTrue(qa.reauth_prompt.winfo_viewable())
        self.assertEqual(self.app.state(), "withdrawn")
        qa.reauth_prompt.password.set("Synthetic-only-master-42!")
        qa.reauth_prompt.submit()
        deadline = time.monotonic() + 6
        while qa.summon_popup is None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.assertIsNotNone(qa.summon_popup)
        self.assertTrue(qa.summon_popup.winfo_viewable())
        self.assertEqual(self.app.state(), "withdrawn")

    def test_minimized_prompt_is_visible_and_cancellation_does_not_unlock(self):
        self.app.iconify()
        self.app.update()
        qa = self.app.quick_access
        qa.request_normal()
        self.app.update()
        self.assertTrue(qa.reauth_prompt.winfo_viewable())
        self.assertEqual(self.app.state(), "iconic")
        qa.cancel_request()
        self.assertIsNone(qa.summon_popup)

    def test_enrolled_hello_success_reauthenticates_existing_session(self):
        hello_enrollment.write(self.app.session, prefer=True)
        qa = self.app.quick_access
        with mock.patch.object(quick_access.windows_hello, "verify", return_value="verified") as verifier:
            qa.request_normal()
            deadline = time.monotonic() + 5
            while qa.summon_popup is None and time.monotonic() < deadline:
                self.app.update()
                time.sleep(0.02)
            self.assertIsNotNone(qa.summon_popup)
            self.assertTrue(self.app.session.is_open)
            verifier.assert_called_once()

    def test_hello_failure_and_cancellation_keep_password_fallback(self):
        hello_enrollment.write(self.app.session, prefer=False)
        qa = self.app.quick_access
        for outcome in ("canceled", "device absent", "timeout", "unavailable"):
            with self.subTest(outcome=outcome), mock.patch.object(
                    quick_access.windows_hello, "verify", return_value=outcome):
                qa.request_normal()
                qa.reauth_prompt.use_hello()
                deadline = time.monotonic() + 5
                while qa._auth_worker.is_alive() and time.monotonic() < deadline:
                    self.app.update()
                    time.sleep(0.02)
                self.app.update()
                self.assertIsNone(qa.summon_popup)
                self.assertIsNotNone(qa.reauth_prompt)
                self.assertTrue(qa.reauth_prompt.confirm.cget("state") != "disabled")
                qa.cancel_request()

    def test_hello_result_after_lock_cannot_grant_access(self):
        hello_enrollment.write(self.app.session, prefer=False)
        qa = self.app.quick_access
        ident = qa.request_normal()
        epoch = qa._epoch
        self.app.shell.lock()
        qa._auth_results.put((ident, epoch, "hello", "verified"))
        qa._process_auth_results()
        self.assertIsNone(qa.summon_popup)
        self.assertFalse(self.app.session.is_open)

    def test_locked_vault_does_not_offer_hello(self):
        hello_enrollment.write(self.app.session, prefer=True)
        self.app.shell.lock()
        qa = self.app.quick_access
        qa.request_normal()
        self.assertTrue(qa.request.await_login)
        self.assertIsNone(qa.reauth_prompt._on_hello)
        self.assertIsNone(qa.summon_popup)

    def test_settings_enrollment_requires_master_and_native_verification(self):
        import ui.settings_page as settings_page
        self.app.shell.navigate("settings")
        page = self.app.shell.pages["settings"]
        with mock.patch.object(settings_page, "master_password_prompt",
                               return_value="wrong synthetic password"), \
             mock.patch.object(settings_page.windows_hello, "verify", return_value="verified") as verifier:
            page._enroll_hello()
            deadline = time.monotonic() + 5
            while page._hello_busy and time.monotonic() < deadline:
                self.app.update()
                time.sleep(0.02)
            self.assertIsNone(hello_enrollment.read(self.app.session))
            verifier.assert_not_called()
        with mock.patch.object(settings_page, "master_password_prompt",
                               return_value="Synthetic-only-master-42!"), \
             mock.patch.object(settings_page.windows_hello, "availability", return_value="available"), \
             mock.patch.object(settings_page.windows_hello, "verify", return_value="verified") as verifier:
            page._enroll_hello()
            deadline = time.monotonic() + 5
            while page._hello_busy and time.monotonic() < deadline:
                self.app.update()
                time.sleep(0.02)
            self.assertEqual(hello_enrollment.read(self.app.session), {"prefer": False})
            self.assertEqual(verifier.call_args.kwargs["purpose"], "enroll")
        page._prefer_hello("on")
        self.assertEqual(hello_enrollment.read(self.app.session), {"prefer": True})
        page._disable_hello()
        self.assertIsNone(hello_enrollment.read(self.app.session))
        page._hello_results.put(("enroll", (page._hello_generation - 1, "verified")))
        page._hello_busy = True
        page._poll_hello()
        self.assertIsNone(hello_enrollment.read(self.app.session))
        self.assertTrue(page._hello_busy)

    def test_autolock_during_hello_discards_late_verification(self):
        hello_enrollment.write(self.app.session, prefer=False)
        qa = self.app.quick_access
        entered = threading.Event()
        release = threading.Event()
        def delayed(_hwnd, **_kwargs):
            entered.set()
            release.wait(3)
            return "verified"
        with mock.patch.object(quick_access.windows_hello, "verify", side_effect=delayed):
            qa.request_normal()
            qa.reauth_prompt.use_hello()
            self.assertTrue(entered.wait(2))
            self.app.shell.lock()
            release.set()
            deadline = time.monotonic() + 4
            while qa._auth_worker.is_alive() and time.monotonic() < deadline:
                self.app.update()
                time.sleep(0.02)
            self.app.update()
            self.assertIsNone(qa.summon_popup)
            self.assertFalse(self.app.session.is_open)

    def test_settings_can_disable_and_reenable_per_user_startup(self):
        import ui.settings_page as settings_page
        self.app.shell.navigate("settings")
        page = self.app.shell.pages["settings"]
        with mock.patch.object(settings_page, "sync_startup", return_value="disabled") as startup:
            page._on_startup("off")
            startup.assert_called_once_with(False)
        self.assertFalse(app_settings.get("start_with_windows"))
        with mock.patch.object(settings_page, "sync_startup", return_value="enabled") as startup:
            page._on_startup("on")
            startup.assert_called_once_with(True)
        self.assertTrue(app_settings.get("start_with_windows"))
        with mock.patch.object(settings_page, "sync_cold_start_links", return_value="enabled") as links:
            page._on_cold_start("on")
            links.assert_called_once_with(True)
        self.assertTrue(app_settings.get("cold_start_shortcuts"))

    def test_minimized_app_can_show_summon(self):
        self.app.iconify()
        self.app.update()
        self.authenticate_summon()
        self.app.update()
        self.assertTrue(self.app.quick_access.summon_popup.winfo_viewable())

    def test_clipboard_clears_only_its_own_synthetic_copy(self):
        self.authenticate_summon()
        memory = {"value": ""}
        with mock.patch.object(quick_access.clipboard.pyperclip, "copy",
                               side_effect=lambda value: memory.__setitem__("value", value)), \
             mock.patch.object(quick_access.clipboard.pyperclip, "paste",
                               side_effect=lambda: memory["value"]):
            self.assertTrue(self.app.quick_access.copy_field(self.entry["id"], "password"))
            self.assertEqual(memory["value"], "SyntheticSecret!")
            quick_access.clipboard._clear_if_ours()
            self.assertEqual(memory["value"], "")
            self.assertTrue(self.app.quick_access.copy_field(self.entry["id"], "password"))
            memory["value"] = "Unrelated synthetic clipboard text"
            quick_access.clipboard._clear_if_ours()
            self.assertEqual(memory["value"], "Unrelated synthetic clipboard text")
            quick_access.clipboard.clear_now()

    def test_hotkey_dispatch_and_no_repeat(self):
        qa = self.app.quick_access
        now = time.monotonic()
        with mock.patch.object(quick_access, "active_desktop_available", return_value=True):
            qa.hotkeys.events.put((now, "summon"))
            qa._poll()
            self.assertIsNotNone(qa.reauth_prompt)
            self.assertIsNone(qa.summon_popup)
            request_id = qa.request.ident
            qa.hotkeys.events.put((now, "summon"))
            qa._poll()
            self.assertEqual(qa.request.ident, request_id)
            qa.cancel_request()
            qa.hotkeys.events.put((time.monotonic(), "voice"))
            qa._poll()
            self.assertIsNone(qa.request)
            self.assertIsNone(qa.summon_popup)


@unittest.skipUnless(sys.platform == "win32", "Windows RegisterHotKey check")
class WindowsHotkeyTests(unittest.TestCase):
    def test_register_and_release_non_shift_chord(self):
        hotkeys = WindowsHotkeys()
        try:
            status = hotkeys.configure("ctrl+alt+n")
            self.assertTrue(status["summon"] == "active" or status["summon"].startswith("unavailable"))
            self.assertEqual(set(status), {"summon"})
        finally:
            hotkeys.stop()
        self.assertFalse(hotkeys._thread and hotkeys._thread.is_alive())

    def test_system_hotkey_from_focused_test_window(self):
        import ctypes
        import tkinter as tk

        hotkeys = WindowsHotkeys()
        root = tk.Tk()
        try:
            root.title("Synthetic Nasolt hotkey test")
            root.geometry("200x80+80+80")
            root.update()
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetForegroundWindow.restype = ctypes.c_void_p
            user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
            user32.GetAncestor.restype = ctypes.c_void_p
            test_hwnd = user32.GetAncestor(root.winfo_id(), 2)
            user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
            user32.SetForegroundWindow(test_hwnd)
            root.focus_force()
            root.update()
            if user32.GetForegroundWindow() != test_hwnd:
                self.skipTest("Synthetic test window could not take foreground focus")
            registration = hotkeys.configure("ctrl+alt+n")["summon"]
            if registration != "active":
                self.skipTest(registration)
            user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte,
                                           ctypes.c_ulong, ctypes.c_ulonglong)
            for code in (0x11, 0x12, ord("N")):
                user32.keybd_event(code, 0, 0, 0)
            for code in (ord("N"), 0x12, 0x11):
                user32.keybd_event(code, 0, 2, 0)
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline and hotkeys.events.empty():
                root.update()
                time.sleep(0.01)
            self.assertFalse(hotkeys.events.empty())
            self.assertEqual(hotkeys.events.get_nowait()[1], "summon")
        finally:
            hotkeys.stop()
            root.destroy()
