"""generator_page.py — Password Generator screen."""
from __future__ import annotations

import tkinter
import customtkinter as ctk

import icons
from generators import PasswordGenerator, estimate_strength
from ui import theme as T
from ui.widgets import Btn, IconBtn, StrengthMeter, Tooltip, check, groupbox, slider


class GeneratorPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self.v_len = ctk.IntVar(value=16)
        self.v = {k: ctk.BooleanVar(value=True) for k in ("lower", "upper", "digits", "symbols")}
        self.v["ambiguous"] = ctk.BooleanVar(value=False)
        self._pw = ""
        self._job = None
        self._build()
        self.regenerate()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Password Generator", font=T.font(16, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=26, pady=(12, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=26, pady=(14, 0))
        body.grid_columnconfigure(1, weight=1)

        left_box, left = groupbox(body, "Password options")
        left_box.grid(row=0, column=0, sticky="new", padx=(0, 18))
        ctk.CTkLabel(left, text="Length", font=T.font(12), text_color=T.TEXT, anchor="w").pack(fill="x")
        self.slider = slider(left, 8, 64, command=self._on_len, width=300)
        self.slider.set(self.v_len.get())
        self.slider.pack(fill="x", pady=(6, 0))
        self.len_lbl = ctk.CTkLabel(left, text="16", font=T.font(12), text_color=T.TEXT, anchor="e")
        self.len_lbl.pack(fill="x", pady=(3, 8))
        for key, text in (("lower", "Lowercase (a-z)"), ("upper", "Uppercase (A-Z)"), ("digits", "Numbers (0-9)"),
                          ("symbols", "Symbols (!@#$%...)")):
            check(left, text, self.v[key], command=lambda k=key: self._on_toggle(k)).pack(anchor="w", pady=5)
        amb = ctk.CTkFrame(left, fg_color="transparent")
        amb.pack(anchor="w", pady=5)
        check(amb, "Exclude ambiguous characters", self.v["ambiguous"], command=lambda: self._on_toggle("ambiguous")).pack(side="left")
        info = ctk.CTkLabel(amb, text="", image=icons.icon("info", 15, T.TEXT_FAINT), width=22)
        info.pack(side="left", padx=(2, 0))
        Tooltip(info, "Leaves out look-alike characters such as 0 / O and 1 / l / I")

        right_box, right = groupbox(body, "Generated password")
        right_box.grid(row=0, column=1, sticky="new")
        top = ctk.CTkFrame(right, fg_color=T.SURFACE, border_width=1,
                           border_color=T.BORDER_STRONG, corner_radius=0)
        top.pack(fill="x", pady=(2, 14))
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(side="right", anchor="n", padx=(0, 7), pady=5)
        IconBtn(btns, "refresh-cw", 16, 27, tooltip="Generate a new password", command=self.regenerate).pack(side="left")
        IconBtn(btns, "copy", 16, 27, tooltip="Copy", command=lambda: self.copy(True)).pack(side="left", padx=(2, 0))
        self.pw_lbl = ctk.CTkLabel(top, text="", font=T.font(16, mono=True), text_color=T.TEXT,
                                   anchor="w", justify="left", wraplength=320)
        self.pw_lbl.pack(side="left", fill="x", expand=True, padx=12, pady=9)
        top.bind("<Configure>", lambda e: self.pw_lbl.configure(wraplength=max(120, int(e.width / T.widget_scale(self)) - 115)))
        mid = ctk.CTkFrame(right, fg_color="transparent")
        mid.pack(fill="x")
        ctk.CTkLabel(mid, text="Strength", font=T.font(12), text_color=T.TEXT, anchor="w").pack(fill="x", pady=(0, 6))
        self.meter = StrengthMeter(mid, segments=4, label_width=110)
        self.meter.pack(fill="x")
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        Btn(row, "Copy", "primary", icon="copy", width=105, height=32, command=lambda: self.copy(True)).pack(side="left")
        Btn(row, "Copy without auto-clear", "secondary", width=190, height=32,
            command=lambda: self.copy(False)).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------ behaviour
    def _on_len(self, v: float) -> None:
        self.v_len.set(int(v))
        self.len_lbl.configure(text=str(int(v)))
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(30, self.regenerate)

    def _on_toggle(self, key: str) -> None:
        if not any(self.v[k].get() for k in ("lower", "upper", "digits", "symbols")):
            self.v[key].set(True)
            self.shell.notify("At least one type required", "Keep one character type selected.", "error")
            return
        self.regenerate()

    def regenerate(self) -> None:
        gen = PasswordGenerator(
            length=self.v_len.get(), use_lowercase=self.v["lower"].get(), use_uppercase=self.v["upper"].get(),
            use_digits=self.v["digits"].get(), use_symbols=self.v["symbols"].get(), exclude_ambiguous=self.v["ambiguous"].get())
        self._pw = gen.generate()
        self.pw_lbl.configure(text=self._pw)
        r = estimate_strength(self._pw)
        self.meter.set(r["entropy_bits"], r["label"])

    def copy(self, auto_clear: bool) -> None:
        self.shell.copy(self._pw, "Password", clear=auto_clear)

    def destroy(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tkinter.TclError:
                pass
            self._job = None
        super().destroy()
