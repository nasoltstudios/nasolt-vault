"""Synthetic Windows UI checks for save failures and page initialization."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


@unittest.skipUnless(sys.platform == "win32", "Windows GUI check")
class UiIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_ui_integrity_", dir=Path(__file__).parent)
        self.env = mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": self.temp.name})
        self.env.start()
        from nasolt_vault import vault
        from nasolt_vault.main import App

        self.vault_paths = mock.patch.multiple(vault, VAULT_DIR=self.temp.name,
                                               VAULT_FILE=str(Path(self.temp.name) / "vault.enc"))
        self.vault_paths.start()
        self.app = App()
        self.app.session.create("Synthetic-only-master-42!")
        self.app.on_unlocked([], [])
        self.app.update()

    def tearDown(self):
        if self.app.winfo_exists():
            self.app.close()
        self.vault_paths.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_failed_saves_do_not_claim_success_or_discard_edits(self):
        from nasolt_vault.ui.entry_dialog import EntryDialog

        shell = self.app.shell
        with mock.patch.object(shell, "_persist", return_value=False):
            self.assertFalse(shell.add_entry({"title": "Synthetic account", "password": "synthetic-only"}))
            self.assertEqual(shell.entries, [])
            self.assertIsNone(shell.add_group("Synthetic group"))
            self.assertEqual(shell.groups, [])
            rows = [{"title": "Imported synthetic", "username": "", "password": "fake-value",
                     "url": "", "notes": "", "group": "", "created": "", "modified": ""}]
            self.assertIsNone(shell.import_rows(rows))
            self.assertEqual(shell.entries, [])

        shell.navigate("transfer")
        transfer = shell.pages["transfer"]
        transfer._rows = rows
        from nasolt_vault.ui import transfer_page as transfer_module
        with mock.patch.object(transfer_module, "confirm", return_value=True), \
             mock.patch.object(shell, "import_rows", return_value=None), \
             mock.patch.object(shell, "notify") as notify:
            transfer._import()
        self.assertIs(transfer._rows, rows)
        notify.assert_not_called()

        dialog = EntryDialog(self.app, [], on_save=lambda fields, ident: False)
        try:
            dialog.title_f.set("Unsaved synthetic account")
            dialog._save()
            self.assertTrue(dialog.winfo_exists())
            self.assertIsNone(dialog.result)
            self.assertIn("still here", dialog.err.cget("text"))
            self.assertEqual(dialog.title_f.get(), "Unsaved synthetic account")
        finally:
            dialog.destroy()

    def test_pages_initialize_and_timer_failure_locks(self):
        shell = self.app.shell
        for name in ("groups", "generator", "lockout_lab", "transfer", "settings", "vault"):
            shell.navigate(name)
            self.app.update()
            self.assertEqual(shell.current, name)
        with mock.patch.object(self.app, "idle_seconds", side_effect=RuntimeError("synthetic timer failure")):
            shell._tick()
        self.assertIsNone(self.app.shell)
        self.assertIsNotNone(self.app.login)
        self.assertFalse(self.app.session.is_open)

    def test_menu_bar_add_entry_opens_dialog_from_another_page(self):
        from nasolt_vault.ui.entry_dialog import EntryDialog
        from nasolt_vault.ui.modal import Modal

        shell = self.app.shell
        shell.navigate("settings")
        self.assertIs(shell.add_entry_button.master.master, shell)
        seen = {}
        deadline = time.monotonic() + 5

        def inspect_dialog():
            if not Modal.open_modals and time.monotonic() < deadline:
                self.app.after(50, inspect_dialog)
                return
            seen["page"] = shell.current
            seen["dialog"] = bool(Modal.open_modals) and isinstance(Modal.open_modals[-1], EntryDialog)
            if Modal.open_modals:
                Modal.open_modals[-1].cancel()

        self.app.after(50, inspect_dialog)
        shell.add_entry_button.invoke()
        self.assertEqual(seen, {"page": "vault", "dialog": True})

    def test_reopen_same_synthetic_vault_and_logo_cache(self):
        from nasolt_vault.main import App
        from nasolt_vault import app_settings
        import customtkinter as ctk
        from nasolt_vault import icons

        self.assertTrue(self.app.shell.add_entry({"title": "Synthetic reopen", "password": "fake-only"}))
        first = icons.avatar_image("Atlas")
        second = icons.avatar_image("Air")
        self.assertIsNot(first, second)
        app_settings.set_value("autolock_minutes", 5)
        app_settings.set_value("theme", "dark")  # Legacy preference must not turn the app dark.
        self.assertIn('"theme": "dark"', Path(app_settings.settings_file()).read_text(encoding="utf-8"))
        self.app.close()
        self.app = App()
        self.assertEqual(self.app.login.mode, "unlock")
        self.assertEqual(ctk.get_appearance_mode(), "Light")
        self.assertIsNone(app_settings.get("theme"))
        entries, groups = self.app.session.open("Synthetic-only-master-42!")
        self.app.on_unlocked(entries, groups)
        self.app.update()
        self.assertEqual([entry["title"] for entry in self.app.shell.entries], ["Synthetic reopen"])
        self.assertEqual(self.app.shell.autolock_minutes, 5)
        self.app.shell.navigate("settings")
        self.assertFalse(hasattr(self.app.shell.pages["settings"], "theme_dd"))

    def test_xp_vault_row_and_transfer_at_minimum_window_size(self):
        from nasolt_vault.ui.vault_page import MASK

        self.app.geometry("980x620")
        shell = self.app.shell
        self.assertTrue(shell.add_entry({"title": "Synthetic row", "username": "test@example.test",
                                         "password": "fake", "url": "example.test"}))
        self.app.update()
        page = shell.pages["vault"]
        row = page._cards[shell.entries[0]["id"]]
        self.assertTrue(row.winfo_ismapped())
        self.assertEqual(row.pass_val.cget("text"), MASK)
        row.toggle_reveal()
        self.assertEqual(row.pass_val.cget("text"), "fake")
        row.toggle_reveal()
        self.assertEqual(row.pass_val.cget("text"), MASK)

        shell.navigate("transfer")
        self.app.update()
        transfer = shell.pages["transfer"]
        self.assertTrue(transfer.scroll.winfo_ismapped())
        self.assertTrue(transfer.file_lbl.winfo_exists())

    def test_encrypted_transfer_uses_password_and_authenticates_before_preview(self):
        from nasolt_vault import export
        from nasolt_vault.ui import transfer_page as transfer_module

        shell = self.app.shell
        self.assertTrue(shell.add_entry({"title": "Synthetic export", "password": "fictional-entry-value"}))
        shell.navigate("transfer")
        page = shell.pages["transfer"]
        self.assertEqual(page.fmt.get(), "NVE")
        passphrase = "fictional-export-passphrase-42"
        with mock.patch.object(page, "_export_dir", return_value=self.temp.name), \
             mock.patch.object(transfer_module, "export_password_prompt", return_value=passphrase), \
             mock.patch.object(shell, "notify"):
            page._export()
        path = page._last_export
        self.assertTrue(path.endswith(".nve"))
        self.assertEqual(export.read_import_file(path, password=passphrase)[0]["password"],
                         "fictional-entry-value")
        with mock.patch.object(transfer_module.filedialog, "askopenfilename", return_value=path), \
             mock.patch.object(transfer_module, "export_password_prompt", return_value="wrong-synthetic-value"), \
             mock.patch.object(transfer_module, "alert") as warning:
            page._choose()
        self.assertIsNone(page._rows)
        warning.assert_called_once()
        with mock.patch.object(transfer_module.filedialog, "askopenfilename", return_value=path), \
             mock.patch.object(transfer_module, "export_password_prompt", return_value=passphrase):
            page._choose()
        self.assertEqual(page._rows[0]["password"], "fictional-entry-value")
        self.assertEqual(len(shell.entries), 1)

    def test_legacy_nsv_requires_confirmation_and_imports_empty_groups(self):
        from nasolt_vault.ui import transfer_page as transfer_module
        from test_legacy_nsv import PASSWORD, fictional_payload, legacy_blob

        shell = self.app.shell
        shell.navigate("transfer")
        page = shell.pages["transfer"]
        path = Path(self.temp.name, "fictional-legacy.nsv")
        path.write_bytes(legacy_blob(fictional_payload() | {"entries": [],
                                                           "groups": ["Empty recovery route"]}))
        vault_path = Path(self.temp.name, "vault.enc")
        before = vault_path.read_bytes()
        with mock.patch.object(transfer_module.filedialog, "askopenfilename", return_value=str(path)) as picker, \
             mock.patch.object(transfer_module, "export_password_prompt", return_value=PASSWORD):
            page._choose()
        self.assertIn("*.nsv", str(picker.call_args.kwargs["filetypes"]))
        self.assertEqual(len(page._rows), 0)
        with mock.patch.object(transfer_module, "confirm", return_value=False) as confirmation, \
             mock.patch.object(shell, "import_rows") as writer:
            page._import()
        confirmation.assert_called_once()
        writer.assert_not_called()
        self.assertEqual(vault_path.read_bytes(), before)
        self.assertEqual(shell.groups, [])
        with mock.patch.object(transfer_module, "confirm", return_value=True):
            page._import()
        self.assertEqual([g["name"] for g in shell.groups], ["Empty recovery route"])
        self.assertIsNone(page._rows)

    def test_new_entry_shows_offline_account_icon_preview(self):
        from nasolt_vault import icons
        from nasolt_vault.ui.entry_dialog import EntryDialog

        self.assertEqual(icons.match_brand("GitHub", ""), "github")
        self.assertIsNotNone(icons.brand_image("github", 24))
        dialog = EntryDialog(self.app, [], on_save=lambda fields, ident: True)
        try:
            dialog.title_f.set("GitHub")
            dialog._refresh_badge()
            self.assertEqual(dialog.title_f._badge_size, 24)
            self.assertIs(dialog.title_f._badge.cget("image"), icons.brand_image("github", 24))
            dialog.title_f.set("Synthetic unknown account")
            dialog._refresh_badge()
            self.assertEqual(dialog.title_f._badge_size, 24)
            self.assertIsNotNone(icons.entry_icon("Synthetic unknown account", size=20))
        finally:
            dialog.close()

    def test_xp_slider_mouse_and_keyboard_update_length(self):
        self.app.shell.navigate("generator")
        page = self.app.shell.pages["generator"]
        control = page.slider
        self.app.update()
        control.set(16)
        control._slider_canvas.focus_set()
        control._slider_canvas.event_generate("<Right>")
        self.assertEqual(control.get(), 17)
        control._slider_canvas.event_generate("<Button-1>", x=control._slider_canvas.winfo_width() - 10,
                                               y=12)
        self.assertEqual(control.get(), 64)

    def test_export_password_modal_confirms_and_collects_masked_value(self):
        from nasolt_vault.ui.modal import Modal, export_password_prompt
        from nasolt_vault.ui.widgets import Field

        value = "synthetic-export-passphrase-42"
        seen = {}

        def fill_fields():
            dialog = Modal.open_modals[-1]
            pending = [dialog.body]
            fields = []
            while pending:
                current = pending.pop()
                for child in current.winfo_children():
                    if isinstance(child, Field):
                        fields.append(child)
                    else:
                        pending.append(child)
            seen["field_count"] = len(fields)
            for field in fields:
                field.set(value)
            seen["shows"] = [field.entry.cget("show") for field in fields]
            dialog._default_action()

        self.app.after(130, fill_fields)
        self.assertEqual(export_password_prompt(self.app, confirm=True), value)
        self.assertEqual(seen, {"field_count": 2, "shows": ["•", "•"]})

    def test_pending_animation_is_cancelled_when_control_closes(self):
        import customtkinter as ctk
        from nasolt_vault.ui.anim import animate

        control = ctk.CTkFrame(self.app.shell.page_host)
        control.pack()
        animate(control, "synthetic", 1000, lambda progress: None)
        self.assertIn("synthetic", control._anims)
        control.destroy()
        self.assertEqual(control._anims, {})

    def test_lock_cancels_pending_generator_and_meter_callbacks(self):
        self.app.shell.navigate("generator")
        page = self.app.shell.pages["generator"]
        page._on_len(25)
        self.app.shell.lock()
        orphans = [job for job in self.app.tk.call("after", "info")
                   if not self.app.tk.call("info", "commands",
                                           str(self.app.tk.call("after", "info", job)[0]).split()[0])]
        self.assertEqual(orphans, [])
        self.app.update()
        self.assertIsNotNone(self.app.login)

    def test_destroyed_tooltip_cancels_its_delay(self):
        import customtkinter as ctk
        from nasolt_vault.ui.widgets import Tooltip

        control = ctk.CTkLabel(self.app.shell.page_host, text="Synthetic tip")
        control.pack()
        tip = Tooltip(control, "Synthetic tooltip")
        tip._schedule()
        job = tip._job
        control.destroy()
        self.assertNotIn(job, self.app.tk.call("after", "info"))

    def test_quickly_closed_dialog_cancels_delayed_tk_callbacks(self):
        from nasolt_vault.ui.modal import Modal

        dialog = Modal(self.app, "Synthetic dialog", 320, 180)
        dialog.present()
        commands = set(dialog._tclCommands or [])

        def owned_jobs():
            return [job for job in dialog.tk.call("after", "info")
                    if str(dialog.tk.call("after", "info", job)[0]).split()[0] in commands]

        self.assertTrue(owned_jobs())
        dialog.close()
        self.assertFalse(owned_jobs())

    def test_modal_action_buttons_are_inside_the_visible_dialog(self):
        from nasolt_vault.ui.modal import Modal, alert, confirm, export_password_prompt, master_password_prompt, prompt
        from nasolt_vault.ui.widgets import Btn

        cases = (
            (lambda: master_password_prompt(self.app), {"Continue", "Cancel"}),
            (lambda: confirm(self.app, "Synthetic confirmation", "Synthetic action?"), {"Confirm", "Cancel"}),
            (lambda: alert(self.app, "Synthetic notice", "Synthetic message"), {"OK"}),
            (lambda: prompt(self.app, "Synthetic name", "Name"), {"Save", "Cancel"}),
            (lambda: export_password_prompt(self.app, confirm=True), {"Encrypt", "Cancel"}),
            (lambda: export_password_prompt(self.app, confirm=False), {"Decrypt", "Cancel"}),
        )
        for open_dialog, expected in cases:
            observed = {}

            def inspect():
                dialog = Modal.open_modals[-1]
                dialog.update_idletasks()
                left, top = dialog.winfo_rootx(), dialog.winfo_rooty()
                right, bottom = left + dialog.winfo_width(), top + dialog.winfo_height()
                for button in dialog.body.winfo_children():
                    for child in button.winfo_children():
                        if isinstance(child, Btn):
                            x, y = child.winfo_rootx(), child.winfo_rooty()
                            observed[child.cget("text")] = (
                                bool(child.winfo_ismapped()) and left <= x and top <= y and
                                x + child.winfo_width() <= right and y + child.winfo_height() <= bottom
                            )
                dialog.cancel()

            self.app.after(150, inspect)
            open_dialog()
            self.assertEqual(set(observed), expected)
            self.assertTrue(all(observed.values()), observed)

    def test_hello_enrollment_master_prompt_continue_button_submits(self):
        from nasolt_vault.ui.modal import Modal, master_password_prompt
        from nasolt_vault.ui.widgets import Btn, Field

        observed = {}
        deadline = time.monotonic() + 2.5

        def submit():
            dialog = Modal.open_modals[-1]
            field = next(child for child in dialog.body.winfo_children() if isinstance(child, Field))
            footer = next(child for child in dialog.body.winfo_children()
                          if any(isinstance(button, Btn) for button in child.winfo_children()))
            button = next(child for child in footer.winfo_children()
                          if isinstance(child, Btn) and child.cget("text") == "Continue")
            if not button.winfo_ismapped() and time.monotonic() < deadline:
                self.app.after(30, submit)
                return
            observed["visible"] = bool(button.winfo_ismapped())
            field.set("Synthetic-only-master-42!")
            button.invoke()

        self.app.after(150, submit)
        watchdog = self.app.after(3000, lambda: Modal.open_modals[-1].cancel() if Modal.open_modals else None)
        result = master_password_prompt(self.app, title="Enroll Windows Hello")
        self.app.after_cancel(watchdog)
        self.assertTrue(observed.get("visible"))
        self.assertEqual(result, "Synthetic-only-master-42!")

    def test_xp_scrollbar_only_when_list_overflows(self):
        from nasolt_vault import vault

        self.app.geometry("980x620")
        shell = self.app.shell
        page = shell.pages["vault"]
        self.app.update()
        self.assertFalse(page.body._scrollbar.winfo_ismapped())
        shell.entries.extend(vault._default_entry(title=f"Synthetic {i}", password="fake-only")
                             for i in range(45))
        shell._refresh_current()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not page.body._scrollbar.winfo_ismapped():
            self.app.update()
            time.sleep(0.02)
        self.assertTrue(page.body._scrollbar.winfo_ismapped())
        shell.entries.clear()
        shell._refresh_current()
        self.app.update()
        self.assertFalse(page.body._scrollbar.winfo_ismapped())

    def test_xp_menu_shortcut_and_keyboard_navigation(self):
        from nasolt_vault.ui.widgets import Popup, open_menu
        from nasolt_vault.ui import theme as T

        shell = self.app.shell
        self.app.focus_force()
        self.app.event_generate("<Alt-f>")
        self.app.update()
        menu = Popup.current
        self.assertIsNotNone(menu)
        self.assertTrue(menu.is_open)
        self.assertEqual(menu._focus_index, 0)
        self.assertEqual(menu._buttons[0].cget("fg_color"), T.MENU_SELECT)
        self.assertEqual(menu._buttons[0].cget("text_color"), T.ON_ACCENT)
        self.assertIs(self.app.focus_get(), menu._buttons[0]._text_label)
        self.app.focus_get().event_generate("<Down>")
        self.assertEqual(menu._focus_index, 1)
        self.app.focus_get().event_generate("<Return>")
        self.assertEqual(shell.current, "transfer")
        self.assertIsNone(Popup.current)

        shell.open_app_menu("Edit")
        self.app._fullscreen = True
        with mock.patch.object(self.app, "attributes") as attributes:
            self.app.event_generate("<Escape>")
            self.app.update()
            self.assertIsNone(Popup.current)
            self.assertTrue(self.app._fullscreen)
            self.assertFalse(any(call.args and call.args[0] == "-fullscreen"
                                 for call in attributes.call_args_list))
        self.app._fullscreen = False

        invoked = []
        menu = open_menu(shell.menu_buttons["file"][0], [
            {"label": "Synthetic action", "icon": "check", "command": lambda: invoked.append(True)}
        ])
        self.app.update()
        self.assertIs(self.app.focus_get(), menu._buttons[0]._text_label)
        self.app.focus_get().event_generate("<Return>")
        self.assertEqual(invoked, [True])
        self.assertFalse(menu.is_open)

    def test_xp_task_header_uses_light_palette(self):
        import tkinter
        import customtkinter as ctk
        from nasolt_vault.ui import theme as T

        shell = self.app.shell
        tasks = shell.nav_items["vault"].master.master
        head = tasks.winfo_children()[0]
        top_band = next(child for child in head.winfo_children() if type(child) is tkinter.Frame)
        self.assertEqual(top_band.cget("bg"), T.TITLEBAR_BANDS[0])
        self.assertEqual(ctk.get_appearance_mode(), "Light")

    def test_xp_command_button_face_and_hover_from_text(self):
        from nasolt_vault.ui import theme as T

        button = self.app.shell.add_entry_button
        self.assertEqual(button.cget("fg_color"), T.BUTTON_FACE)
        self.assertEqual(button.cget("border_color"), T.BORDER_STRONG)
        button._text_label.event_generate("<Enter>")
        self.assertEqual(button.cget("fg_color"), T.BUTTON_HOVER)
        self.assertEqual(button.cget("border_color"), T.BUTTON_HOT_BORDER)
        button._text_label.event_generate("<Leave>")
        self.assertEqual(button.cget("fg_color"), T.BUTTON_FACE)
        self.assertEqual(button.cget("border_color"), T.BORDER_STRONG)

    def test_xp_menu_spans_window_and_sidebar_has_no_brand_titlebar(self):
        import customtkinter as ctk

        shell = self.app.shell
        self.app.update()
        menu = shell.winfo_children()[0]
        self.assertEqual(menu.winfo_width(), shell.winfo_width())
        self.assertIs(shell.add_entry_button.master, menu)
        self.assertTrue(shell.add_entry_button.winfo_ismapped())
        side = shell.nav_items["vault"].master.master.master
        stack = [side]
        texts = []
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            if isinstance(widget, ctk.CTkLabel):
                texts.append(widget.cget("text"))
        self.assertNotIn("Nasolt Vault", texts)

    def test_native_windows_frame_uses_square_corners(self):
        if sys.platform != "win32" or sys.getwindowsversion().build < 22000:
            self.skipTest("Windows 11 native frame attribute")
        import ctypes
        from nasolt_vault.ui import theme as T

        self.assertTrue(T.style_native_window(self.app))
        user32 = ctypes.WinDLL("user32")
        user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.GetAncestor.restype = ctypes.c_void_p
        hwnd = user32.GetAncestor(self.app.winfo_id(), 2)
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmGetWindowAttribute.argtypes = (
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
        dwm.DwmGetWindowAttribute.restype = ctypes.c_long
        corners = ctypes.c_uint32()
        self.assertEqual(dwm.DwmGetWindowAttribute(hwnd, 33, ctypes.byref(corners), 4), 0)
        self.assertEqual(corners.value, 1)

    def test_xp_dropdown_can_be_used_from_keyboard(self):
        from nasolt_vault.ui.widgets import Popup

        shell = self.app.shell
        dropdown = shell.pages["vault"].filter_dd
        self.app.update()
        dropdown.focus_set()
        self.assertIs(self.app.focus_get(), dropdown._canvas)
        self.app.focus_get().event_generate("<Return>")
        self.app.update()
        menu = Popup.current
        self.assertIsNotNone(menu)
        self.assertIs(self.app.focus_get(), menu._buttons[0]._text_label)
        self.app.focus_get().event_generate("<Down>")
        self.app.focus_get().event_generate("<Return>")
        self.assertEqual(shell.filter_group, "__none__")
        self.assertIsNone(Popup.current)

    def test_dialog_dropdown_enter_does_not_save_entry(self):
        from nasolt_vault.ui.entry_dialog import EntryDialog
        from nasolt_vault.ui.widgets import Btn, Popup
        from nasolt_vault import vault

        group = vault.add_group([], "Synthetic group")
        save = mock.Mock(return_value=True)
        dialog = EntryDialog(self.app, [group], on_save=save)
        try:
            dialog.title_f.set("Synthetic account")
            dialog.present()
            time.sleep(0.1)
            self.app.update()
            self.assertIs(self.app.focus_get(), dialog.title_f.entry._entry)
            dialog.group_dd.focus_set()
            self.app.focus_get().event_generate("<Return>")
            self.app.update()
            self.assertIsNotNone(Popup.current)
            # Other Windows GUI tests may change OS focus between dialogs.
            # Start this keyboard check on the dropdown's first menu item.
            Popup.current._focus(0)
            self.app.focus_get().event_generate("<Down>")
            self.app.focus_get().event_generate("<Return>")
            self.assertEqual(dialog.group_dd.get(), group["id"])
            save.assert_not_called()
            self.assertTrue(dialog.winfo_exists())
            stack = [dialog.body]
            buttons = []
            while stack:
                parent = stack.pop()
                for child in parent.winfo_children():
                    if isinstance(child, Btn):
                        buttons.append(child)
                    else:
                        stack.append(child)
            save_button = next(button for button in buttons if button.cget("text") == "Save")
            save_button._canvas.focus_set()
            self.app.focus_get().event_generate("<Return>")
            save.assert_called_once()
            self.assertFalse(dialog.winfo_exists())
        finally:
            Popup.close_current()
            dialog.close()

    def test_xp_buttons_activate_once_from_keyboard(self):
        import customtkinter as ctk
        from nasolt_vault.ui.widgets import Btn, IconBtn

        calls = []
        host = ctk.CTkFrame(self.app.shell.page_host, width=260, height=90)
        host.place(x=10, y=100)
        try:
            button = Btn(host, "Synthetic action", command=lambda: calls.append("text"))
            button.pack(side="left")
            icon = IconBtn(host, "check", command=lambda: calls.append("icon"))
            icon.pack(side="left")
            self.app.update()
            for control in (button, icon):
                control._canvas.focus_set()
                control._canvas.event_generate("<Return>")
            self.assertEqual(calls, ["text", "icon"])
            button.set_enabled(False)
            button._canvas.focus_set()
            button._canvas.event_generate("<Return>")
            self.assertEqual(calls, ["text", "icon"])
        finally:
            host.destroy()

    def test_create_failure_does_not_show_exception_contents(self):
        self.app.show_login()
        self.app.login._created({"e": RuntimeError("synthetic-private-path-or-secret")})
        self.assertNotIn("synthetic-private-path-or-secret", self.app.login.err.cget("text"))
        self.assertIn("Couldn't create", self.app.login.err.cget("text"))


if __name__ == "__main__":
    unittest.main()
