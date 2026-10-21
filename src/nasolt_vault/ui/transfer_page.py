"""transfer_page.py — Import / Export."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter.filedialog as filedialog
from typing import Optional

import customtkinter as ctk

from .. import app_settings
from .. import export as export_mod
from .. import icons
from ..paths import default_export_dir
from . import theme as T
from .modal import alert, confirm, export_password_prompt
from .widgets import Btn, Dropdown, Field, card, fit_text, style_scrollbar

MAX_W = 880


def _disc(parent, icon_name: str) -> ctk.CTkFrame:
    d = ctk.CTkFrame(parent, width=46, height=46, corner_radius=2, fg_color=T.ACCENT_SOFT)
    d.pack_propagate(False)
    ctk.CTkLabel(d, text="", image=icons.icon(icon_name, 22, T.TEXT)).place(relx=0.5, rely=0.5, anchor="center")
    return d


def open_folder(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class TransferPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._rows: Optional[list] = None
        self._file = ""
        self._last_export = ""
        self._build()
        self.bind("<Configure>", self._limit, add="+")

    def _limit(self, _e=None) -> None:
        extra = max(0, int(self.winfo_width() / T.widget_scale(self)) - 52 - MAX_W)
        self.col.pack_configure(padx=(26, 26 + extra))

    def _export_dir(self) -> str:
        return app_settings.get_export_dir() or default_export_dir()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Import / Export", font=T.font(16, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=26, pady=(12, 0))
        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.ACCENT)
        style_scrollbar(self.scroll)
        self.scroll.pack(fill="both", expand=True)
        self.col = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.col.pack(fill="x", padx=26, pady=(12, 24))

        # ---------------- export
        ex = card(self.col)
        ex.pack(fill="x")
        head = ctk.CTkFrame(ex, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(22, 0))
        _disc(head, "download").pack(side="left")
        t = ctk.CTkFrame(head, fg_color="transparent")
        t.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(t, text="Export Vault", font=T.font(17, "bold"), text_color=T.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(t, text="Save entries to an encrypted file or a plaintext format.", font=T.font(13), text_color=T.TEXT_MUTED, anchor="w").pack(anchor="w")

        grid = ctk.CTkFrame(ex, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=(18, 0))
        grid.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(grid, text="Format", font=T.font(13), text_color=T.TEXT, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ctk.CTkLabel(grid, text="Destination Folder", font=T.font(13), text_color=T.TEXT, anchor="w").grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 6))
        self.fmt = Dropdown(grid, [("NVE", "Encrypted (.nve)"), ("JSON", "JSON (plaintext)"),
                                   ("CSV", "CSV (plaintext)")], value="NVE", width=200)
        self.fmt.grid(row=1, column=0, sticky="w")
        self.dest = Field(grid, readonly=True, width=300)
        self.dest.grid(row=1, column=1, sticky="ew", padx=(14, 8))
        self.dest.set(self._export_dir())
        Btn(grid, "Browse...", "secondary", width=104, command=self._browse).grid(row=1, column=2)

        foot = ctk.CTkFrame(ex, fg_color="transparent")
        foot.pack(fill="x", padx=24, pady=(18, 0))
        Btn(foot, "Export", "primary", width=132, height=40, command=self._export).pack(side="left")
        self.last_lbl = ctk.CTkLabel(foot, text="", font=T.font(12), text_color=T.TEXT_MUTED, anchor="w")
        self.last_lbl.pack(side="left", padx=(14, 0))
        self.show_btn = Btn(foot, "Show in folder", "link", width=110, height=30, size=12, command=lambda: open_folder(os.path.dirname(self._last_export)))
        note = ctk.CTkFrame(ex, fg_color="transparent")
        note.pack(fill="x", padx=24, pady=(12, 20))
        ctk.CTkLabel(note, text="", image=icons.icon("triangle-alert", 14, T.WARNING), width=18).pack(side="left")
        ctk.CTkLabel(note, text="Encrypted exports need their export password. CSV and JSON contain plaintext passwords.",
                     font=T.font(12), text_color=T.TEXT_MUTED, anchor="w", justify="left").pack(side="left", padx=(6, 0))

        # ---------------- import
        im = card(self.col)
        im.pack(fill="x", pady=(18, 0))
        head = ctk.CTkFrame(im, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(22, 0))
        _disc(head, "upload").pack(side="left")
        t = ctk.CTkFrame(head, fg_color="transparent")
        t.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(t, text="Import Vault", font=T.font(17, "bold"), text_color=T.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(t, text="Merge entries from an encrypted, CSV, or JSON file.", font=T.font(13), text_color=T.TEXT_MUTED, anchor="w").pack(anchor="w")
        row = ctk.CTkFrame(im, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(18, 22))
        Btn(row, "Choose File...", "secondary", width=130, height=40, command=self._choose).pack(side="left")
        self.file_lbl = ctk.CTkLabel(row, text="No file selected.", font=T.font(13), text_color=T.TEXT_MUTED, anchor="w")
        self.file_lbl.pack(side="left", padx=(14, 0))
        self.import_btn = Btn(row, "Import", "primary", width=112, height=40, command=self._import)

    # ------------------------------------------------------------ export
    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Choose export folder", initialdir=self._export_dir() if os.path.isdir(self._export_dir()) else None,
                                         parent=self.winfo_toplevel())
        if chosen:
            chosen = os.path.normpath(chosen)
            app_settings.set_export_dir(chosen)
            self.dest.set(chosen)

    def _export(self) -> None:
        fmt = self.fmt.get()
        password = None
        if fmt == "NVE":
            password = export_password_prompt(self.winfo_toplevel(), confirm=True)
            if password is None:
                return
        elif not confirm(self.winfo_toplevel(), "Plaintext export",
                         "CSV and JSON files contain readable passwords. Continue with a plaintext export?",
                         confirm_text="Export plaintext"):
            return
        try:
            path = export_mod.export_vault(self.shell.entries, fmt, self._export_dir(), self.shell.groups,
                                           password=password)
        except Exception as e:
            alert(self.winfo_toplevel(), "Export failed", str(e))
            return
        self._last_export = path
        self.dest.set(os.path.dirname(path))
        self.last_lbl.configure(text=fit_text(os.path.basename(path), T.font(12), 330))
        self.show_btn.pack(side="left", padx=(4, 0))
        n = len(self.shell.entries)
        self.shell.notify("Export complete", f"{n} {'entry' if n == 1 else 'entries'} saved to {os.path.basename(path)}")

    # ------------------------------------------------------------ import
    def _choose(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a file to import", parent=self.winfo_toplevel(),
            filetypes=[("Vault exports", "*.nve *.nsv *.csv *.json"), ("Encrypted Nasolt export", "*.nve *.nsv"),
                       ("CSV", "*.csv"), ("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._reset_import()
        password = None
        if os.path.splitext(path)[1].lower() in (".nve", ".nsv"):
            password = export_password_prompt(self.winfo_toplevel(), confirm=False)
            if password is None:
                return
        try:
            rows = export_mod.read_import_file(path, password=password)
        except Exception as e:
            self._reset_import()
            alert(self.winfo_toplevel(), "Can't import this file", str(e))
            return
        self._rows, self._file = rows, path
        known = {g["name"].lower() for g in self.shell.groups}
        group_names = [r["group"] for r in rows if r.get("group")]
        group_names.extend(getattr(rows, "group_names", ()))
        new_groups = {name.strip().lower() for name in group_names if name.strip() and name.strip().lower() not in known}
        extra = f" · {len(new_groups)} new {'group' if len(new_groups) == 1 else 'groups'}" if new_groups else ""
        self.file_lbl.configure(text=fit_text(f"{os.path.basename(path)} — {len(rows)} {'entry' if len(rows) == 1 else 'entries'}{extra}", T.font(13), 380),
                                text_color=T.TEXT)
        self.import_btn.pack(side="right")

    def _reset_import(self) -> None:
        self._rows, self._file = None, ""
        self.file_lbl.configure(text="No file selected.", text_color=T.TEXT_MUTED)
        self.import_btn.pack_forget()

    def _import(self) -> None:
        if self._rows is None:
            return
        group_count = len(getattr(self._rows, "group_names", ()))
        detail = f" and up to {group_count} groups" if group_count else ""
        if not confirm(self.winfo_toplevel(), "Confirm import",
                       f"Import {len(self._rows)} entries{detail} into this vault?",
                       confirm_text="Import"):
            return
        res = self.shell.import_rows(self._rows)
        if res is None:
            return
        bits = [f"{res.added} added"]
        if res.skipped:
            bits.append(f"{res.skipped} duplicate{'s' if res.skipped != 1 else ''} skipped")
        if res.groups_created:
            bits.append(f"{res.groups_created} group{'s' if res.groups_created != 1 else ''} created")
        self.shell.notify("Import complete", ", ".join(bits) + ".")
        self._reset_import()
