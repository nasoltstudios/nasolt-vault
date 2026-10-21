"""groups_page.py — Groups: master (list) / detail (actions) layout."""
from __future__ import annotations

from typing import Dict, Optional

import customtkinter as ctk

from .. import icons
from . import theme as T
from .anim import cancel, tween_color
from .modal import confirm, prompt
from .widgets import Btn, card, divider, hand, style_scrollbar

NONE_KEY = "__none__"


class GroupRow(ctk.CTkFrame):
    def __init__(self, master, key: str, name: str, count: int, icon_name: str, icon_color, subtitle: str,
                 on_select, on_open):
        super().__init__(master, fg_color="transparent", corner_radius=0, height=42 if subtitle else 38)
        self.key = key
        self.pack_propagate(False)
        self._selected = False
        self.bar = ctk.CTkFrame(self, width=3, fg_color=T.ACCENT_LINE, corner_radius=0)
        ctk.CTkLabel(self, text="", image=icons.icon(icon_name, 18, icon_color), width=24).pack(side="left", padx=(12, 6))
        col = ctk.CTkFrame(self, fg_color="transparent")
        col.pack(side="left", fill="y", pady=3)
        self.name_lbl = ctk.CTkLabel(col, text=name, font=T.font(12), text_color=T.TEXT, anchor="w")
        self.name_lbl.pack(anchor="w", expand=True)
        if subtitle:
            ctk.CTkLabel(col, text=subtitle, font=T.font(11), text_color=T.TEXT_MUTED, anchor="w").pack(anchor="w")
        ctk.CTkLabel(self, text=str(count), font=T.font(12), text_color=T.TEXT_MUTED).pack(side="right", padx=(0, 14))
        for w in [self] + list(self.winfo_children()) + list(col.winfo_children()):
            w.bind("<Button-1>", lambda e: on_select(key), add="+")
            w.bind("<Double-Button-1>", lambda e: on_open(key), add="+")
            w.bind("<Enter>", lambda e: self._hover(True), add="+")
            w.bind("<Leave>", lambda e: self._hover(False), add="+")
            hand(w)

    def _hover(self, on: bool) -> None:
        if self._selected:
            return
        a, b = T.resolve(T.SURFACE), T.resolve(T.SURFACE_2)
        tween_color(self, "fg_color", a if on else b, b if on else a, 110, final=T.SURFACE_2 if on else "transparent", key="bg")

    def set_selected(self, on: bool) -> None:
        cancel(self, "bg")
        self._selected = on
        self.configure(fg_color=T.ACCENT_SOFT if on else "transparent")
        if on:
            self.bar.place(x=0, y=0, relheight=1)
        else:
            self.bar.place_forget()


class GroupsPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._selected: Optional[str] = None
        self._rows: Dict[str, GroupRow] = {}
        self._seen_version = -1
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=26, pady=(10, 0))
        ctk.CTkLabel(head, text="Groups", font=T.font(16, "bold"),
                     text_color=T.TEXT).pack(side="left")
        Btn(head, "New Group", "secondary", icon="plus", width=118, height=30,
            command=self.new_group).pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=26, pady=(14, 24))
        self.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(body, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=T.BORDER_STRONG,
                                      scrollbar_button_hover_color=T.TEXT_FAINT)
        style_scrollbar(left)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self.list_card = card(left)
        self.list_card.pack(fill="x")
        self.none_card = card(left)
        self.none_card.pack(fill="x", pady=(5, 0))

        right = card(body, width=272)
        right.grid(row=0, column=1, sticky="new")
        ctk.CTkLabel(right, text="Group Actions", font=T.font(12, "bold"), text_color=T.TEXT_MUTED, anchor="w").pack(fill="x", padx=16, pady=(12, 7))
        divider(right).pack(fill="x", padx=16)
        self.btn_open = Btn(right, "Open in My Vault", "ghost", icon="folder-open", anchor="w", width=230, height=30, command=self.open_selected)
        self.btn_open.pack(fill="x", padx=8, pady=(7, 0))
        self.btn_rename = Btn(right, "Rename", "ghost", icon="pencil", anchor="w", width=230, height=30, command=self.rename_selected)
        self.btn_rename.pack(fill="x", padx=8, pady=(1, 0))
        self.btn_delete = Btn(right, "Delete", "danger_ghost", icon="trash-2", anchor="w", width=230, height=30, command=self.delete_selected)
        self.btn_delete.pack(fill="x", padx=8, pady=(1, 0))
        note = ctk.CTkFrame(right, fg_color="transparent")
        note.pack(fill="x", padx=16, pady=(10, 13))
        ctk.CTkLabel(note, text="", image=icons.icon("info", 14, T.TEXT_FAINT), width=18).pack(side="left", anchor="n", pady=2)
        ctk.CTkLabel(note, text="Deleting a group will unassign its entries, not delete them.", font=T.font(12),
                     text_color=T.TEXT_MUTED, wraplength=210, justify="left", anchor="w").pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------ data
    def refresh(self) -> None:
        self._seen_version = self.shell.data_version
        sh = self.shell
        for w in self.list_card.winfo_children() + self.none_card.winfo_children():
            w.destroy()
        self._rows.clear()

        def count(gid) -> int:
            return sum(1 for e in sh.entries if (e.get("group_id") or None) == gid)

        if sh.groups:
            for i, g in enumerate(sh.groups):
                if i:
                    divider(self.list_card).pack(fill="x")
                row = GroupRow(self.list_card, g["id"], g["name"], count(g["id"]), "folder", T.FOLDER, "", self._select, self._open)
                row.pack(fill="x", padx=1, pady=(1 if i == 0 else 0, 1 if i == len(sh.groups) - 1 else 0))
                self._rows[g["id"]] = row
        else:
            f = ctk.CTkFrame(self.list_card, fg_color="transparent")
            f.pack(fill="x", pady=26)
            ctk.CTkLabel(f, text="", image=icons.icon("folder-plus", 30, T.TEXT_FAINT)).pack()
            ctk.CTkLabel(f, text="No groups yet", font=T.font(15, "bold"), text_color=T.TEXT).pack(pady=(8, 0))
            ctk.CTkLabel(f, text="Create a group to organize your entries.", font=T.font(12), text_color=T.TEXT_MUTED).pack()

        row = GroupRow(self.none_card, NONE_KEY, "Ungrouped", count(None), "folder-open", T.TEXT_MUTED,
                       "", self._select, self._open)
        row.pack(fill="x", padx=1, pady=1)
        self._rows[NONE_KEY] = row

        if self._selected not in self._rows:
            self._selected = next(iter(self._rows))
        self._select(self._selected)

    def _select(self, key: str) -> None:
        self._selected = key
        for k, r in self._rows.items():
            r.set_selected(k == key)
        is_none = key == NONE_KEY
        self.btn_rename.set_enabled(not is_none)
        self.btn_delete.set_enabled(not is_none)

    # ------------------------------------------------------------ actions
    def _open(self, key: str) -> None:
        self.shell.open_group(None if key == NONE_KEY else key)

    def open_selected(self) -> None:
        if self._selected:
            self._open(self._selected)

    def _validator(self, exclude_id: Optional[str] = None):
        def check(value: str) -> Optional[str]:
            if not value:
                return "Please enter a group name."
            if len(value) > 40:
                return "Keep the name under 40 characters."
            if value.lower() == "ungrouped" or any(g["name"].lower() == value.lower() and g["id"] != exclude_id for g in self.shell.groups):
                return "A group with this name already exists."
            return None
        return check

    def new_group(self) -> None:
        name = prompt(self.winfo_toplevel(), "New Group", "Group name", placeholder="e.g. Finance", confirm_text="Create",
                      validate=self._validator())
        if name:
            g = self.shell.add_group(name)
            if g is not None:
                self._selected = g["id"]
                self.refresh()

    def rename_selected(self) -> None:
        g = next((g for g in self.shell.groups if g["id"] == self._selected), None)
        if not g:
            return
        name = prompt(self.winfo_toplevel(), "Rename Group", "New name", initial=g["name"], confirm_text="Rename",
                      validate=self._validator(g["id"]))
        if name and name != g["name"]:
            self.shell.rename_group(g["id"], name)
            self.refresh()

    def delete_selected(self) -> None:
        g = next((g for g in self.shell.groups if g["id"] == self._selected), None)
        if not g:
            return
        n = sum(1 for e in self.shell.entries if e.get("group_id") == g["id"])
        detail = f"\n\n{n} {'entry' if n == 1 else 'entries'} in this group will become Ungrouped (they are not deleted)." if n else ""
        if confirm(self.winfo_toplevel(), "Delete group?", f'Delete the group "{g["name"]}"?{detail}', "Delete", danger=True):
            self.shell.delete_group(g["id"])
            self._selected = None
            self.refresh()
