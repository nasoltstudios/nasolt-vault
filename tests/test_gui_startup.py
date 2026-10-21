"""Windows startup regression: the first CustomTkinter window must stay visible."""
from __future__ import annotations

import os
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


class StartupDiagnosticsTests(unittest.TestCase):
    def test_startup_error_reports_phase_without_exception_value(self):
        from nasolt_vault import main

        captured = io.StringIO()
        with mock.patch.object(main, "setup_logging"), \
             mock.patch.object(main, "App", side_effect=RuntimeError("synthetic-secret-value")), \
             mock.patch("sys.stderr", captured), \
             mock.patch.object(main.logging, "getLogger") as get_logger:
            self.assertEqual(main.main(), 1)
        report = captured.getvalue()
        self.assertIn("window initialization: RuntimeError", report)
        self.assertNotIn("synthetic-secret-value", report)
        self.assertNotIn("synthetic-secret-value", str(get_logger.mock_calls))


@unittest.skipUnless(sys.platform == "win32", "Windows GUI startup check")
class GuiStartupTests(unittest.TestCase):
    def test_quick_login_swap_cancels_pending_callbacks(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_gui_callbacks_", dir=Path(__file__).parent) as temp:
            with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": temp}):
                from nasolt_vault import vault
                from nasolt_vault.main import App

                with mock.patch.multiple(vault, VAULT_DIR=temp, VAULT_FILE=str(Path(temp) / "vault.enc")):
                    app = App()
                    try:
                        app.login._error("Synthetic error", app.login.f_pw)
                        app.login._set_mode("create")
                        app.show_login()
                        orphans = [job for job in app.tk.call("after", "info")
                                   if not app.tk.call("info", "commands",
                                                      str(app.tk.call("after", "info", job)[0]).split()[0])]
                        self.assertEqual(orphans, [])
                        app.update()
                        self.assertTrue(app.winfo_viewable())
                    finally:
                        if app.winfo_exists():
                            app.close()

    def test_login_window_visible_and_interactive_after_mainloop_starts(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_gui_startup_", dir=Path(__file__).parent) as temp:
            with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": temp}):
                from nasolt_vault import vault
                from nasolt_vault.main import App

                with mock.patch.multiple(vault, VAULT_DIR=temp, VAULT_FILE=str(Path(temp) / "vault.enc")):
                    app = App()
                    seen: dict[str, object] = {}

                    def inspect() -> None:
                        seen["state"] = app.state()
                        seen["viewable"] = bool(app.winfo_viewable())
                        seen["login"] = app.login is not None
                        app.login.btn_create.invoke()
                        seen["mode"] = app.login.mode
                        app.close()

                    app.after(450, inspect)
                    app.mainloop()
                    self.assertEqual(seen, {"state": "normal", "viewable": True,
                                            "login": True, "mode": "create"})

    def test_login_controls_create_lock_and_reopen_synthetic_vault(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_gui_login_", dir=Path(__file__).parent) as temp:
            with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": temp}):
                from nasolt_vault import vault
                from nasolt_vault.main import App

                with mock.patch.multiple(vault, VAULT_DIR=temp, VAULT_FILE=str(Path(temp) / "vault.enc")):
                    app = App()
                    try:
                        app.update()
                        self.assertEqual(app.login.mode, "create")
                        app.login.f_pw.set("Synthetic-only-master-42!")
                        app.login.f_confirm.set("Synthetic-only-master-42!")
                        app.login.submit.invoke()

                        def await_shell() -> bool:
                            deadline = time.monotonic() + 15
                            while time.monotonic() < deadline:
                                app.update()
                                if app.shell is not None:
                                    return True
                                time.sleep(0.02)
                            return False

                        self.assertTrue(await_shell(), "Create form did not open the synthetic vault")
                        app.shell.lock()
                        app.update()
                        self.assertEqual(app.login.mode, "unlock")
                        app.login.f_pw.set("Synthetic-only-master-42!")
                        app.login.submit.invoke()
                        self.assertTrue(await_shell(), "Unlock form did not reopen the synthetic vault")
                        self.assertTrue(app.winfo_viewable())
                    finally:
                        if app.winfo_exists():
                            app.close()
