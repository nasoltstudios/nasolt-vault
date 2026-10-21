"""
Nasolt Vault — local, offline, encrypted password manager.
Single window: a login view that is swapped for the unlocked app (no second Tk root).
"""
from __future__ import annotations

import sys

if "--selftest" in sys.argv:            # headless packaging check used by build.py — must run before any GUI import
    from .selftest import run as _selftest
    sys.exit(_selftest())

if "--migrate-vault" in sys.argv:       # installer-only ciphertext copy; no GUI or secrets in output
    from .installer_migration import cli as _migrate
    index = sys.argv.index("--migrate-vault")
    sys.exit(_migrate(sys.argv[index + 1] if len(sys.argv) == index + 2 else None))

if "--installer-shortcuts" in sys.argv:  # no GUI or vault access
    from .installer_shortcuts import cli as _shortcuts
    index = sys.argv.index("--installer-shortcuts")
    sys.exit(_shortcuts(sys.argv[index + 1:]))

import logging
import os
import time
import tkinter
import traceback

import customtkinter as ctk

from . import clipboard
from . import app_settings
from . import icons
from .quick_access import QuickAccess
from .windows_startup import cleanup_legacy_voice_link, sync_startup, sync_cold_start_links
from .windows_tray import TrayIcon
from .paths import data_dir, resource_path
from .ui import theme as T
from .ui.anim import animate
from .ui.login import LoginView
from .ui.modal import Modal
from .ui.shell import Shell
from .ui.widgets import Popup, Toasts
from .vault import VaultSession

LOGIN_SIZE = (940, 560)
MAIN_SIZE = (1280, 820)
MAIN_MIN = (980, 620)


def setup_logging() -> None:
    try:
        logging.basicConfig(filename=os.path.join(data_dir(), "nasolt_vault.log"), level=logging.WARNING,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except OSError:
        logging.basicConfig(level=logging.WARNING)


class App(ctk.CTk):
    def __init__(self, initial_route: str | None = None, background: bool = False, instance=None) -> None:
        T.apply_mode()
        super().__init__(fg_color=T.BG)
        T.reset_tk_cache()
        icons.reset_tk_cache()
        self.withdraw()
        self.title("Nasolt Vault")
        self._set_icon()
        self.session = VaultSession()
        self.instance = instance
        self.last_activity = time.monotonic()
        self._last_wall = time.time()
        self.shell: Shell | None = None
        self.login: LoginView | None = None
        self.toasts = Toasts(self)
        self.tray = TrayIcon()
        self.quick_access = QuickAccess(self)
        self._fullscreen = False
        self._close_wait_job = None
        self._background_start = background
        self._tray_deadline = 0.0
        self._close_tray_job = None

        for seq in ("<Motion>", "<Key>", "<Button>", "<MouseWheel>"):
            self.bind(seq, self._touch, add="+")
        self.bind("<Control-n>", lambda e: self.shell and self.shell.new_entry())
        self.bind("<Control-f>", lambda e: self.shell and self.shell.focus_search())
        self.bind("<Control-l>", lambda e: self.shell and self.shell.lock())
        for key, label in (("f", "File"), ("e", "Edit"), ("v", "View"), ("t", "Tools")):
            self.bind(f"<Alt-{key}>", lambda e, name=label: self.shell and self.shell.open_app_menu(name))
        self.bind("<F10>", lambda e: self.shell and self.shell.open_app_menu("File"))
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen, add="+")
        self.protocol("WM_DELETE_WINDOW", self.on_window_close)
        self.report_callback_exception = self._tk_error

        self._initializing_window = True
        self.show_login()
        # CustomTkinter's first Windows update applies the title-bar color and
        # can withdraw the root. Finish it before showing an interactive window.
        self.update()
        self._initializing_window = False
        if background and self.tray.start_async():
            self._tray_deadline = time.monotonic() + 10
            self.after(50, self._finish_background_start)
        else:
            self.after(1, self._reveal_initial_window)
        if initial_route == "normal":
            self.after(1, self.quick_access.request_normal)

    def _reveal_initial_window(self) -> None:
        self.state("normal")
        self.deiconify()
        T.style_native_window(self)
        self.lift()
        self.focus_force()
        animate(self, "reveal", 200, lambda t: self._alpha(t))
        self.toasts_raise()

    def _finish_background_start(self) -> None:
        if not self._background_start:
            return
        if self.tray.active:
            self._background_start = False
            return
        if self.tray._ready.is_set() or time.monotonic() >= self._tray_deadline:
            self._background_start = False
            self._reveal_initial_window()
            return
        self.after(50, self._finish_background_start)

    # ------------------------------------------------------------ window helpers
    def _set_icon(self) -> None:
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(resource_path("assets", "app.ico"))
            else:
                self._icon_img = tkinter.PhotoImage(file=resource_path("assets", "app.png"))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _touch(self, _e=None) -> None:
        self.last_activity = time.monotonic()
        self._last_wall = time.time()

    def idle_seconds(self) -> float:
        """Seconds since the last keyboard / mouse activity. Uses the larger of the monotonic and wall clocks
        so time spent asleep (when a monotonic clock may pause) still counts toward auto-lock."""
        return max(time.monotonic() - self.last_activity, time.time() - self._last_wall, 0.0)

    def _swap(self, build, size, min_size, resizable: bool, reveal: bool = True) -> None:
        """Rebuild the window contents off-screen, resize + centre, then fade in."""
        self.withdraw()
        self.toasts.clear()
        if self._fullscreen:
            self.attributes("-fullscreen", False)
            self._fullscreen = False
        if not self._initializing_window and reveal:
            self.state("normal")
        for child in self.winfo_children():
            if isinstance(child, (LoginView, Shell)):
                child.destroy()
        self.resizable(resizable, resizable)
        T.fit_window(self, size[0], size[1], *min_size)
        build()
        self.update_idletasks()
        try:
            self.attributes("-alpha", 0.0 if reveal and not self._initializing_window else 1.0)
        except tkinter.TclError:
            pass
        if not self._initializing_window and reveal:
            self.deiconify()
            T.style_native_window(self)
            self.lift()
            self.focus_force()
            animate(self, "reveal", 200, lambda t: self._alpha(t))
            self.toasts_raise()

    def _alpha(self, v: float) -> None:
        try:
            self.attributes("-alpha", v)
        except tkinter.TclError:
            pass

    def toasts_raise(self) -> None:
        for it in self.toasts._items:
            it["frame"].tkraise()

    # ------------------------------------------------------------ flow
    def show_login(self, message: str | None = None, preserve_hidden: bool = False) -> None:
        self.quick_access.revoke()
        clipboard.clear_now()
        self.session.close()
        Popup.close_current()
        self.shell = None

        def build() -> None:
            self.login = LoginView(self, self, message)
            self.login.pack(fill="both", expand=True)

        self._swap(build, LOGIN_SIZE, LOGIN_SIZE, resizable=False, reveal=not preserve_hidden)

    def on_unlocked(self, entries, groups, reveal: bool = True) -> None:
        self.login = None
        self._touch()

        def build() -> None:
            self.shell = Shell(self, self, self.session, entries, groups)
            self.shell.pack(fill="both", expand=True)

        self._swap(build, MAIN_SIZE, MAIN_MIN, resizable=True, reveal=reveal)
        self.quick_access.on_session_unlocked()

    def open_window(self) -> None:
        self._background_start = False
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def open_settings(self) -> None:
        self.open_window()
        if self.shell is not None:
            self.shell.navigate("settings")

    def lock_from_tray(self) -> None:
        was_hidden = self.state() == "withdrawn"
        self.show_login(preserve_hidden=was_hidden)

    def tray_action(self, action: str) -> None:
        if action == "open":
            self.open_window()
        elif action == "lock":
            self.lock_from_tray()
        elif action == "settings":
            if self.session.is_open:
                self.open_settings()
            else:
                self.quick_access.request_normal("settings")
        elif action == "exit":
            self.close()

    def on_window_close(self) -> None:
        self._background_start = False
        if app_settings.get("close_to_tray", True):
            self.show_login(preserve_hidden=True)
            if self.tray.active:
                return
            if self.tray.start_async():
                self._tray_deadline = time.monotonic() + 10
                if self._close_tray_job is None:
                    self._close_tray_job = self.after(50, self._finish_close_to_tray)
                return
        self.close()

    def _finish_close_to_tray(self) -> None:
        self._close_tray_job = None
        if self.tray.active:
            return
        if self.tray._ready.is_set() or time.monotonic() >= self._tray_deadline:
            self.close()
            return
        self._close_tray_job = self.after(50, self._finish_close_to_tray)

    def _toggle_fullscreen(self, _e=None) -> None:
        if self.shell is None:
            return
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def _exit_fullscreen(self, _e=None) -> None:
        from .ui.widgets import Popup
        if Popup.current is not None:
            return
        if self._fullscreen:
            self._fullscreen = False
            self.attributes("-fullscreen", False)

    def close(self) -> None:
        # Unlock/create/recovery runs on a worker. Let it finish its encrypted
        # file operation before releasing the session lock and closing Tk.
        self.quick_access.cancel_native_authentication()
        worker = getattr(self.login, "_active_worker", None)
        quick_worker = getattr(self.quick_access, "_auth_worker", None)
        if ((worker is not None and worker.is_alive()) or
                (quick_worker is not None and quick_worker.is_alive())):
            if self._close_wait_job is None:
                self._close_wait_job = self.after(50, self._retry_close)
            return
        try:
            # Tk keeps scheduled callbacks after their widget is destroyed.
            # Cancel them before shutdown so a later root in this process does
            # not receive stale callbacks from this window.
            try:
                for job in self.tk.call("after", "info"):
                    # Each owning widget deletes its Tcl command in destroy().
                    self.tk.call("after", "cancel", job)
            except tkinter.TclError:
                pass
            clipboard.clear_now()
            self.quick_access.stop()
            self.tray.stop()
            self.session.close()
            Modal.close_all()
        finally:
            self.destroy()

    def _retry_close(self) -> None:
        self._close_wait_job = None
        self.close()

    # ------------------------------------------------------------ errors
    def _tk_error(self, exc, val, tb) -> None:
        logging.getLogger("nasolt").error("Unhandled UI error: %s at %s", exc.__name__, _error_location(tb))
        try:
            self.toasts.show("Something went wrong", "The action could not finish. Check your vault before trying again.", "error", 6000)
        except Exception:
            pass


def _error_location(tb) -> str:
    """Code location only; exception messages can contain vault or path data."""
    frames = traceback.extract_tb(tb)
    if not frames:
        return "unknown location"
    frame = frames[-1]
    return f"{os.path.basename(frame.filename)}:{frame.lineno} ({frame.name})"


def main() -> int:
    stage = "logging setup"
    instance = None
    try:
        if "--unregister-startup" in sys.argv:
            startup = sync_startup(False)
            links = sync_cold_start_links(False)
            return 0 if startup in ("disabled", "isolated test mode") and links in ("disabled", "isolated test mode") else 1
        if "--voice" in sys.argv:
            # A shortcut from an older build can invoke this before the updated
            # app has started. Remove only that verified app-owned link.
            return 0 if cleanup_legacy_voice_link() in ("removed", "isolated test mode", "Windows only") else 1
        from .instance import InstanceCoordinator
        instance = InstanceCoordinator()
        route = "normal" if "--summon" in sys.argv else "open"
        if not instance.acquire():
            if "--background" not in sys.argv:
                instance.send(route)
            return 0
        setup_logging()
        sync_startup(bool(app_settings.get("start_with_windows", True)))
        stage = "window initialization"
        app = App(initial_route=route if route != "open" else None,
                  background="--background" in sys.argv or route == "normal", instance=instance)
        stage = "event loop"
        app.mainloop()
        return 0
    except Exception as exc:
        summary = f"Nasolt Vault stopped during {stage}: {type(exc).__name__} at {_error_location(exc.__traceback__)}"
        logging.getLogger("nasolt").error("%s", summary)
        try:
            print(summary, file=sys.stderr)
            print("Check nasolt_vault.log in the selected data folder; review it before sharing.", file=sys.stderr)
        except Exception:
            pass
        return 1
    finally:
        if instance is not None:
            instance.close()


if __name__ == "__main__":
    sys.exit(main())
