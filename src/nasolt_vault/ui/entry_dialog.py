"""entry_dialog.py — Add / Edit Entry dialog with live account icon and mini generator."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

from .. import icons
from ..generators import PasswordGenerator, estimate_strength
from . import theme as T
from .modal import Modal
from .widgets import Btn, Dropdown, Field, StrengthMeter, card, divider, slider, style_scrollbar

UNGROUPED_KEY = "__none__"


class EntryDialog(Modal):
    def __init__(self, parent, groups: List[Dict[str, Any]], existing: Optional[Dict[str, Any]] = None,
                 default_group_id: Optional[str] = None,
                 on_save: Optional[Callable[[Dict[str, Any], Optional[str]], bool]] = None):
        screen_h = parent.winfo_screenheight() / T.window_scale(parent)
        height = 660 if screen_h >= 820 else max(470, int(screen_h - 120))
        self._compact = height < 660                       # short screens: the form scrolls, footer stays visible
        super().__init__(parent, "Edit Entry" if existing else "Add Entry", 800, height, default_action=self._save)
        self.existing, self.groups, self.on_save = existing, groups, on_save
        self._gen_open = False
        self._gen_len = 20
        self._build(default_group_id)
        if existing:
            self._load(existing)

    def present(self) -> None:
        super().present()
        self.after(70, self.title_f.focus)

    # ------------------------------------------------------------ layout
    def _build(self, default_group_id: Optional[str]) -> None:
        body = self.body
        right = ctk.CTkFrame(body, fg_color="transparent", width=272)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        divider(body, vertical=True).pack(side="right", fill="y")
        left_wrap = ctk.CTkFrame(body, fg_color="transparent")
        left_wrap.pack(side="left", fill="both", expand=True)
        footer = ctk.CTkFrame(left_wrap, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(8, 18))
        if self._compact:
            left = ctk.CTkScrollableFrame(left_wrap, fg_color="transparent", corner_radius=0,
                                          scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.TEXT_FAINT)
            style_scrollbar(left)
        else:
            left = ctk.CTkFrame(left_wrap, fg_color="transparent")
        left.pack(side="top", fill="both", expand=True)

        pad = dict(padx=24)
        self._label_row(left, "Title", required=True)
        self.title_f = Field(left, "e.g. GitHub")
        self.title_f.pack(fill="x", **pad)
        self.title_f.bind_key(lambda e: self._refresh_badge())

        self._label_row(left, "Username")
        self.user_f = Field(left, "e.g. user@example.com")
        self.user_f.pack(fill="x", **pad)

        self._label_row(left, "Password")
        prow = ctk.CTkFrame(left, fg_color="transparent")
        prow.pack(fill="x", **pad)
        self.pass_f = Field(prow, "Generate a strong password", password=True)
        self.pass_f.pack(side="left", fill="x", expand=True)
        Btn(prow, "Generate", "secondary", icon="refresh-cw", width=108, height=38, command=self._quick_generate).pack(side="left", padx=(8, 0))
        self.meter = StrengthMeter(left, segments=6, label_width=84)
        self.meter.pack(fill="x", padx=24, pady=(6, 0))
        self.pass_f.bind_key(lambda e: self._refresh_meter())

        self._label_row(left, "URL (optional)")
        self.url_f = Field(left, "https://example.com")
        self.url_f.pack(fill="x", **pad)
        self.url_f.bind_key(lambda e: self._refresh_badge())

        self._label_row(left, "Notes (optional)")
        self.notes = ctk.CTkTextbox(left, height=58, fg_color=T.INPUT, border_width=1, border_color=T.BORDER_STRONG,
                                    corner_radius=1, text_color=T.TEXT, font=T.font(13), wrap="word")
        self.notes.pack(fill="x", **pad)

        self._label_row(left, "Group")
        opts = [(UNGROUPED_KEY, "Ungrouped")] + [(g["id"], g["name"]) for g in self.groups]
        start = default_group_id if default_group_id in [k for k, _ in opts] else UNGROUPED_KEY
        self.group_dd = Dropdown(left, opts, value=start, width=300)
        self.group_dd.pack(fill="x", **pad)

        Btn(footer, "Save", "primary", width=92, command=self._save).pack(side="right")
        Btn(footer, "Cancel", "outline", width=92, command=self.cancel).pack(side="right", padx=(0, 10))
        self.err = ctk.CTkLabel(footer, text="", font=T.font(12), text_color=T.DANGER, anchor="w")
        self.err.pack(side="left")

        # ---- right column: generator panel
        panel = card(right, fg_color=T.SURFACE)
        panel.pack(fill="x", padx=18, pady=(18, 0))
        head = ctk.CTkFrame(panel, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(14, 10))
        ctk.CTkLabel(head, text="", image=icons.icon("key-round", 20, T.TEXT), width=24).pack(side="left")
        ctk.CTkLabel(head, text="Password Generator", font=T.font(14, "bold"), text_color=T.TEXT).pack(side="left", padx=(10, 0))
        self.gen_btn = Btn(panel, "Open Generator", "secondary", icon="external-link", icon_right=True, height=38, command=self._toggle_gen)
        self.gen_btn.pack(fill="x", padx=14, pady=(0, 14))
        self.gen_area = ctk.CTkFrame(panel, fg_color="transparent")

        ctk.CTkLabel(self.gen_area, text="Length", font=T.font(12), text_color=T.TEXT_MUTED, anchor="w").pack(fill="x", padx=14)
        srow = ctk.CTkFrame(self.gen_area, fg_color="transparent")
        srow.pack(fill="x", padx=14, pady=(2, 8))
        self.len_val = ctk.CTkLabel(srow, text=str(self._gen_len), font=T.font(13, "bold"), text_color=T.TEXT, width=28)
        self.len_val.pack(side="right")
        self.len_slider = slider(srow, 8, 48, command=self._on_len, width=150)
        self.len_slider.set(self._gen_len)
        self.len_slider.pack(side="left", fill="x", expand=True)
        self.gen_preview = ctk.CTkLabel(self.gen_area, text="", font=T.font(13, mono=True), text_color=T.TEXT, wraplength=210,
                                        justify="left", anchor="w")
        self.gen_preview.pack(fill="x", padx=14, pady=(0, 10))
        Btn(self.gen_area, "Use this password", "primary", height=36, command=self._use_generated).pack(fill="x", padx=14)
        Btn(self.gen_area, "Regenerate", "ghost", icon="refresh-cw", height=34, command=self._regen).pack(fill="x", padx=14, pady=(6, 14))

    def _label_row(self, parent, text: str, required: bool = False) -> None:
        ctk.CTkLabel(parent, text=text + (" *" if required else ""), font=T.font(13), text_color=T.TEXT,
                     anchor="w").pack(fill="x", padx=24, pady=(10, 4))

    # ------------------------------------------------------------ behaviour
    def _load(self, e: Dict[str, Any]) -> None:
        self.title_f.set(e.get("title", ""))
        self.user_f.set(e.get("username", ""))
        self.pass_f.set(e.get("password", ""))
        self.url_f.set(e.get("url", ""))
        self.notes.insert("1.0", e.get("notes", ""))
        gid = e.get("group_id") or UNGROUPED_KEY
        if gid in [k for k, _ in self.group_dd._opts]:
            self.group_dd.set(gid)
        self._refresh_meter()
        self._refresh_badge(pop=False)

    def _refresh_badge(self, pop: bool = True) -> None:
        title, url = self.title_f.get(), self.url_f.get()
        key = (title, url)
        if key == getattr(self, "_badge_key", None):
            return
        self._badge_key = key
        img = icons.entry_icon(title, url, 24) if title.strip() or url.strip() else None
        # A live preview should follow typing without queuing pop animations.
        self.title_f.set_badge(img, pop=False)

    def _refresh_meter(self) -> None:
        pw = self.pass_f.get()
        if not pw:
            self.meter.set(0, "")
            return
        r = estimate_strength(pw)
        self.meter.set(r["entropy_bits"], r["label"])

    def _quick_generate(self) -> None:
        self.pass_f.set(PasswordGenerator(length=20).generate())
        self.pass_f.toggle_reveal(True)
        self._refresh_meter()

    def _toggle_gen(self) -> None:
        self._gen_open = not self._gen_open
        if self._gen_open:
            self.gen_area.pack(fill="x")
            self.gen_btn.configure(text=" Hide Generator")
            self._regen()
        else:
            self.gen_area.pack_forget()
            self.gen_btn.configure(text=" Open Generator")

    def _on_len(self, v: float) -> None:
        self._gen_len = int(v)
        self.len_val.configure(text=str(self._gen_len))
        self._regen()

    def _regen(self) -> None:
        self._preview = PasswordGenerator(length=self._gen_len).generate()
        self.gen_preview.configure(text=self._preview)

    def _use_generated(self) -> None:
        self.pass_f.set(self._preview)
        self.pass_f.toggle_reveal(True)
        self._refresh_meter()

    def _save(self) -> None:
        title = self.title_f.get().strip()
        if not title:
            self.title_f.set_error(True)
            self.err.configure(text="Title is required.")
            self.title_f.focus()
            self.after(2500, lambda: (self.title_f.set_error(False), self.err.configure(text="")) if self.winfo_exists() else None)
            return
        gid = self.group_dd.get()
        fields = {
            "title": title,
            "username": self.user_f.get().strip(),
            "password": self.pass_f.get(),
            "url": self.url_f.get().strip(),
            "notes": self.notes.get("1.0", "end").strip(),
            "group_id": None if gid == UNGROUPED_KEY else gid,
        }
        eid = self.existing["id"] if self.existing else None
        if self.on_save and self.on_save(fields, eid) is False:
            self.err.configure(text="Couldn't save. Your edits are still here.")
            return
        self.close(True)
