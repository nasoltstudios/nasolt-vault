"""
Nasolt Vault — local, offline, encrypted password manager.
Single window: a login view that is swapped for the unlocked app (no second Tk root).
"""
from __future__ import annotations

import sys

if "--selftest" in sys.argv:            # headless packaging check used by build.py — must run before any GUI import
    from selftest import run as _selftest
    sys.exit(_selftest())

if "--migrate-vault" in sys.argv:       # installer-only ciphertext copy; no GUI or secrets in output
    from installer_migration import cli as _migrate
    index = sys.argv.index("--migrate-vault")
    sys.exit(_migrate(sys.argv[index + 1] if len(sys.argv) == index + 2 else None))

import logging
import os
import time
import tkinter
import traceback

import customtkinter as ctk

import clipboard
import icons
from paths import data_dir, resource_path
from ui import theme as T
from ui.anim import animate
from ui.login import LoginView
from ui.modal import Modal
from ui.shell import Shell
from ui.widgets import Popup, Toasts
from vault import VaultSession

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
    def __init__(self) -> None:
        T.apply_mode()
        super().__init__(fg_color=T.BG)
        T.reset_tk_cache()
        icons.reset_tk_cache()
        self.withdraw()
        self.title("Nasolt Vault")
        self._set_icon()
        self.session = VaultSession()
        self.last_activity = time.monotonic()
        self._last_wall = time.time()
        self.shell: Shell | None = None
        self.login: LoginView | None = None
        self.toasts = Toasts(self)
        self._fullscreen = False
        self._close_wait_job = None

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
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.report_callback_exception = self._tk_error

        self._initializing_window = True
        self.show_login()
        # CustomTkinter's first Windows update applies the title-bar color and
        # can withdraw the root. Finish it before showing an interactive window.
        self.update()
        self._initializing_window = False
        self.after(1, self._reveal_initial_window)

    def _reveal_initial_window(self) -> None:
        self.state("normal")
        self.deiconify()
        T.style_native_window(self)
        self.lift()
        self.focus_force()
        animate(self, "reveal", 200, lambda t: self._alpha(t))
        self.toasts_raise()

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

    def _swap(self, build, size, min_size, resizable: bool) -> None:
        """Rebuild the window contents off-screen, resize + centre, then fade in."""
        self.withdraw()
        self.toasts.clear()
        if self._fullscreen:
            self.attributes("-fullscreen", False)
            self._fullscreen = False
        if not self._initializing_window:
            self.state("normal")
        for child in self.winfo_children():
            if isinstance(child, (LoginView, Shell)):
                child.destroy()
        self.resizable(resizable, resizable)
        T.fit_window(self, size[0], size[1], *min_size)
        build()
        self.update_idletasks()
        try:
            self.attributes("-alpha", 0.0)
        except tkinter.TclError:
            pass
        if not self._initializing_window:
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
    def show_login(self, message: str | None = None) -> None:
        self.session.close()
        Popup.close_current()
        self.shell = None

        def build() -> None:
            self.login = LoginView(self, self, message)
            self.login.pack(fill="both", expand=True)

        self._swap(build, LOGIN_SIZE, LOGIN_SIZE, resizable=False)

    def on_unlocked(self, entries, groups) -> None:
        self.login = None
        self._touch()

        def build() -> None:
            self.shell = Shell(self, self, self.session, entries, groups)
            self.shell.pack(fill="both", expand=True)

        self._swap(build, MAIN_SIZE, MAIN_MIN, resizable=True)

    def _toggle_fullscreen(self, _e=None) -> None:
        if self.shell is None:
            return
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def _exit_fullscreen(self, _e=None) -> None:
        from ui.widgets import Popup
        if Popup.current is not None:
            return
        if self._fullscreen:
            self._fullscreen = False
            self.attributes("-fullscreen", False)

    def close(self) -> None:
        # Unlock/create/recovery runs on a worker. Let it finish its encrypted
        # file operation before releasing the session lock and closing Tk.
        worker = getattr(self.login, "_active_worker", None)
        if worker is not None and worker.is_alive():
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
    try:
        setup_logging()
        stage = "window initialization"
        app = App()
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


if __name__ == "__main__":
    sys.exit(main())
