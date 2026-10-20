"""settings_page.py — Settings."""
from __future__ import annotations

import os
import tkinter.filedialog as filedialog

import customtkinter as ctk

import app_settings
from paths import default_export_dir
from ui import theme as T
from ui.widgets import Btn, Dropdown, Field, groupbox

VERSION = "v2.0.0"
MAX_W = 880
AUTOLOCK = [("1", "1 minute"), ("5", "5 minutes"), ("10", "10 minutes"), ("15", "15 minutes"), ("30", "30 minutes"), ("60", "1 hour")]


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._build()
        self.bind("<Configure>", self._limit, add="+")

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
        self.col = ctk.CTkFrame(self, fg_color="transparent")
        self.col.pack(fill="both", expand=True, padx=26, pady=(12, 0))
        s = app_settings.load_settings()

        security, controls = groupbox(self.col, "Vault protection")
        security.pack(fill="x", pady=(0, 13))
        self.auto = self._dd_row(controls, 0, "Auto-lock timeout", "Lock after inactivity.", options=AUTOLOCK,
                                 value=str(self.shell.autolock_minutes), width=190, command=self._on_autolock)
        self._row(controls, 1, "Encryption")
        ctk.CTkLabel(controls, text="AES-256-GCM", font=T.font(12), text_color=T.TEXT,
                     anchor="w").grid(row=1, column=1, sticky="w")

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

    def _change_folder(self) -> None:
        cur = app_settings.get_export_dir() or default_export_dir()
        chosen = filedialog.askdirectory(title="Choose export folder", initialdir=cur if os.path.isdir(cur) else None,
                                         parent=self.winfo_toplevel())
        if chosen:
            chosen = os.path.normpath(chosen)
            app_settings.set_export_dir(chosen)
            self.folder.set(chosen)
            self.shell.notify("Export folder updated", chosen)
