"""settings_page.py — Settings."""
from __future__ import annotations

import os
import queue
import threading
import tkinter.filedialog as filedialog
from tkinter import TclError

import customtkinter as ctk

from .. import app_settings
from .. import hello_enrollment
from .. import windows_hello
from ..windows_startup import sync_startup, sync_cold_start_links
from ..windows_focus import window_handle
from ..paths import default_export_dir
from . import theme as T
from .modal import master_password_prompt
from .widgets import Btn, Dropdown, Field, groupbox

VERSION = "v2.0.0"
MAX_W = 880
AUTOLOCK = [("1", "1 minute"), ("5", "5 minutes"), ("10", "10 minutes"), ("15", "15 minutes"), ("30", "30 minutes"), ("60", "1 hour")]
SUMMON_SHORTCUTS = [("off", "Off"), ("ctrl+alt+n", "Ctrl+Alt+N"),
                    ("ctrl+shift+n", "Ctrl+Shift+N"), ("shift+n", "Shift+N")]
SUMMON_TIMEOUTS = [(str(n), f"{n} seconds") for n in (15, 30, 60, 120)]
ON_OFF = [("on", "On"), ("off", "Off")]


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._hello_results = queue.Queue()
        self._hello_busy = False
        self._hello_generation = 0
        self._hello_cancel = None
        self._build()
        self.bind("<Configure>", self._limit, add="+")
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event):
        if event.widget is self and self._hello_cancel is not None:
            self._hello_cancel.set()

    def _limit(self, _e=None) -> None:
        extra = max(0, int(self.winfo_width() / T.widget_scale(self)) - 64 - MAX_W)
        self.col.pack_configure(padx=(32, 32 + extra))

    def _row(self, parent, r: int, label: str) -> None:
        ctk.CTkLabel(parent, text=label, font=T.font(12), text_color=T.TEXT, anchor="w", width=170).grid(row=r, column=0, sticky="w", pady=6, padx=(0, 14))

    def _dd_row(self, parent, r: int, label: str, hint: str, **dd) -> Dropdown:
        """Dropdown with its hint text right beside it."""
        self._row(parent, r, label)
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=r, column=1, columnspan=3, sticky="w")
        d = Dropdown(holder, **dd)
        d.pack(side="left")
        if hint:
            ctk.CTkLabel(holder, text=hint, font=T.font(11), text_color=T.TEXT_MUTED, anchor="w").pack(side="left", padx=(14, 0))
        return d

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Settings", font=T.font(16, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=26, pady=(12, 0))
        self.col = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.col.pack(fill="both", expand=True, padx=26, pady=(12, 0))
        s = app_settings.load_settings()

        security, controls = groupbox(self.col, "Vault protection")
        security.pack(fill="x", pady=(0, 13))
        self.auto = self._dd_row(controls, 0, "Auto-lock timeout", "Lock after inactivity.", options=AUTOLOCK,
                                 value=str(self.shell.autolock_minutes), width=190, command=self._on_autolock)
        self._row(controls, 1, "Encryption")
        ctk.CTkLabel(controls, text="AES-256-GCM", font=T.font(12), text_color=T.TEXT,
                     anchor="w").grid(row=1, column=1, sticky="w")

        quick, quick_controls = groupbox(self.col, "Quick access")
        quick.pack(fill="x", pady=(0, 13))
        self.summon_shortcut = self._dd_row(
            quick_controls, 0, "Normal authentication", "Then opens Vault Summon.",
            options=SUMMON_SHORTCUTS, value=s.get("summon_shortcut", "ctrl+alt+n"),
            width=170, command=lambda value: self._on_shortcut("summon_shortcut", value))
        self.summon_timeout = self._dd_row(
            quick_controls, 1, "Summon timeout", "Closes after inactivity.",
            options=SUMMON_TIMEOUTS, value=str(s.get("summon_timeout_seconds", 30)),
            width=170, command=self._on_summon_timeout)
        ctk.CTkLabel(quick_controls,
                     text="Global shortcuts reserve their keys. Shift+letter options may interrupt typing.",
                     font=T.font(11), text_color=T.TEXT_MUTED, anchor="w", wraplength=600,
                     justify="left").grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 2))
        self.shortcut_status = ctk.CTkLabel(quick_controls, text="", font=T.font(11),
                                            text_color=T.TEXT_MUTED, anchor="w")
        self.shortcut_status.grid(row=3, column=0, columnspan=4, sticky="w")
        self._show_shortcut_status()

        auth, auth_controls = groupbox(self.col, "Authentication")
        auth.pack(fill="x", pady=(0, 13))
        self._row(auth_controls, 0, "Windows Hello")
        self.hello_status = ctk.CTkLabel(auth_controls, text="Checking availability…",
                                         font=T.font(11), text_color=T.TEXT_MUTED, anchor="w")
        self.hello_status.grid(row=0, column=1, columnspan=3, sticky="w")
        holder = ctk.CTkFrame(auth_controls, fg_color="transparent")
        holder.grid(row=1, column=1, columnspan=3, sticky="w", pady=(2, 4))
        Btn(holder, "Enroll Windows Hello", "secondary", width=167,
            command=self._enroll_hello).pack(side="left", padx=(0, 8))
        Btn(holder, "Disable / reset", "secondary", width=120,
            command=self._disable_hello).pack(side="left")
        self.hello_prefer = self._dd_row(
            auth_controls, 2, "Prefer Hello", "For Ctrl+Alt+N when the vault is already unlocked.",
            options=ON_OFF, value="on" if (hello_enrollment.read(self.shell.session) or {}).get("prefer") else "off",
            width=95, command=self._prefer_hello)
        ctk.CTkLabel(auth_controls,
                     text="The master password is always available and is required when the vault is locked.",
                     font=T.font(11), text_color=T.TEXT_MUTED, anchor="w", wraplength=590,
                     justify="left").grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 4))
        self._refresh_hello_status()

        startup, startup_controls = groupbox(self.col, "Windows background")
        startup.pack(fill="x", pady=(0, 13))
        self.startup = self._dd_row(startup_controls, 0, "Start with Windows",
                                    "Starts locked in the system tray.", options=ON_OFF,
                                    value="on" if s.get("start_with_windows", True) else "off",
                                    width=170, command=self._on_startup)
        self.close_tray = self._dd_row(startup_controls, 1, "Close to tray",
                                       "Use File → Exit to stop the app.", options=ON_OFF,
                                       value="on" if s.get("close_to_tray", True) else "off",
                                       width=170, command=self._on_close_tray)
        self.cold_start = self._dd_row(startup_controls, 2, "Cold-start shortcut",
                                       "Optional Windows Shell shortcut after full exit.", options=ON_OFF,
                                       value="on" if s.get("cold_start_shortcuts", False) else "off",
                                       width=170, command=self._on_cold_start)

        files, file_controls = groupbox(self.col, "Files")
        files.pack(fill="x", pady=(0, 13))
        self._row(file_controls, 0, "Current export folder")
        self.folder = Field(file_controls, readonly=True, width=310, height=32)
        self.folder.grid(row=0, column=1, sticky="w")
        self.folder.set(s.get("export_dir") or default_export_dir())
        Btn(file_controls, "Change...", "secondary", width=94, height=32,
            command=self._change_folder).grid(row=0, column=2, padx=(8, 0), sticky="w")

        ctk.CTkLabel(self.col, text=f"Nasolt Vault  {VERSION}", font=T.font(11),
                     text_color=T.TEXT_MUTED, anchor="w").pack(fill="x", padx=14)


    def _on_autolock(self, key: str) -> None:
        self.shell.set_autolock(int(key))
        self.shell.notify("Auto-lock updated", f"The vault will lock after {dict(AUTOLOCK)[key]} of inactivity.")

    def _refresh_hello_status(self):
        enrolled = hello_enrollment.read(self.shell.session)
        self.hello_status.configure(text="Enrolled for this vault; checking Windows…" if enrolled else
                                    "Not enrolled; checking Windows…")
        def work():
            self._hello_results.put(("availability", windows_hello.availability()))
        threading.Thread(target=work, daemon=True, name="NasoltHelloAvailability").start()
        self.after(50, self._poll_hello)

    def _poll_hello(self):
        try:
            if not self.winfo_exists():
                return
        except TclError:
            return
        try:
            while True:
                kind, result = self._hello_results.get_nowait()
                if kind == "availability" and result is not None:
                    if not self._hello_busy:
                        enrolled = hello_enrollment.read(self.shell.session)
                        self.hello_status.configure(text=f"Windows: {result}; " +
                                                    ("enrolled for this vault" if enrolled else "not enrolled"))
                elif kind == "enroll":
                    generation, result = result
                    if generation != self._hello_generation:
                        continue
                    self._hello_busy = False
                    self._hello_cancel = None
                    if (result == "verified" and self.shell.app.shell is self.shell and
                            self.shell.session.is_open and self.shell.session.matches_disk()):
                        try:
                            hello_enrollment.write(self.shell.session, prefer=False)
                        except (OSError, RuntimeError):
                            result = "could not save enrollment"
                        else:
                            self.hello_prefer.set("off")
                            result = "enrolled"
                    elif result == "verified":
                        result = "session ended; enrollment not saved"
                    self.hello_status.configure(text=f"Windows Hello: {result}.")
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(100, self._poll_hello)
        except TclError:
            pass

    def _enroll_hello(self):
        if self._hello_busy or not self.shell.session.is_open:
            return
        password = master_password_prompt(self, title="Enroll Windows Hello")
        if not password:
            return
        hwnd = window_handle(self.shell.app)
        self._hello_busy = True
        self._hello_generation += 1
        generation = self._hello_generation
        cancel = threading.Event()
        self._hello_cancel = cancel
        self.hello_status.configure(text="Checking master password and Windows Hello…")
        def work(candidate):
            try:
                if not self.shell.session.verify_master_password(candidate):
                    result = "master password not accepted"
                elif windows_hello.availability() != "available":
                    result = "unavailable; check Windows Hello setup"
                else:
                    result = windows_hello.verify(hwnd, cancel=cancel, purpose="enroll")
            except Exception:
                result = "enrollment failed"
            self._hello_results.put(("enroll", (generation, result)))
        threading.Thread(target=work, args=(password,), daemon=True,
                         name="NasoltHelloEnroll").start()

    def _disable_hello(self):
        self._hello_generation += 1
        if self._hello_cancel is not None:
            self._hello_cancel.set()
        self._hello_busy = False
        self._hello_cancel = None
        try:
            hello_enrollment.remove()
        except OSError:
            self.hello_status.configure(text="Could not remove enrollment. Check file access.")
        else:
            self.hello_prefer.set("off")
            self.hello_status.configure(text="Windows Hello enrollment removed.")

    def _prefer_hello(self, value):
        if hello_enrollment.read(self.shell.session) is None:
            self.hello_prefer.set("off")
            self.hello_status.configure(text="Enroll Windows Hello first.")
            return
        try:
            hello_enrollment.write(self.shell.session, prefer=value == "on")
        except (OSError, RuntimeError):
            self.hello_prefer.set("off")
            self.hello_status.configure(text="Could not save preference.")

    def _show_shortcut_status(self) -> None:
        status = self.shell.app.quick_access.status()
        self.shortcut_status.configure(text=f"Global registration: Summon {status['summon']}.")

    def _on_shortcut(self, key: str, value: str) -> None:
        app_settings.set_value(key, value)
        if self.summon_shortcut.get() != "ctrl+alt+n":
            app_settings.set_value("cold_start_shortcuts", False)
            self.cold_start.set("off")
        self.shell.app.quick_access.configure_from_settings()
        self._show_shortcut_status()
        if self.shell.app.quick_access.status()["summon"].startswith("unavailable"):
            self.shell.notify("Shortcut unavailable", "Windows denied registration or another app uses this combination.", "error")

    def _on_summon_timeout(self, value: str) -> None:
        app_settings.set_value("summon_timeout_seconds", int(value))
        self.shell.app.quick_access.configure_from_settings()

    def _on_startup(self, value: str) -> None:
        enabled = value == "on"
        result = sync_startup(enabled)
        if result in ("enabled", "disabled", "isolated test mode"):
            app_settings.set_value("start_with_windows", enabled)
            self.shell.notify("Windows startup updated", "Starts locked in the tray." if enabled else
                              "Automatic startup disabled.")
        else:
            self.startup.set("off" if enabled else "on")
            self.shell.notify("Windows startup unavailable", result, "error")

    def _on_close_tray(self, value: str) -> None:
        app_settings.set_value("close_to_tray", value == "on")

    def _on_cold_start(self, value: str) -> None:
        enabled = value == "on"
        if enabled and self.summon_shortcut.get() != "ctrl+alt+n":
            self.cold_start.set("off")
            self.shell.notify("Use the default shortcut", "Cold start supports Ctrl+Alt+N.", "info")
            return
        result = sync_cold_start_links(enabled)
        if result in ("enabled", "disabled", "isolated test mode"):
            app_settings.set_value("cold_start_shortcuts", enabled)
            self.shell.app.quick_access.configure_from_settings()
            self._show_shortcut_status()
        else:
            self.cold_start.set("off" if enabled else "on")
            self.shell.notify("Cold-start shortcuts unavailable", result, "error")

    def _change_folder(self) -> None:
        cur = app_settings.get_export_dir() or default_export_dir()
        chosen = filedialog.askdirectory(title="Choose export folder", initialdir=cur if os.path.isdir(cur) else None,
                                         parent=self.winfo_toplevel())
        if chosen:
            chosen = os.path.normpath(chosen)
            app_settings.set_export_dir(chosen)
            self.folder.set(chosen)
            self.shell.notify("Export folder updated", chosen)
