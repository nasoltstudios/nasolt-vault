"""vault_page.py — XP Explorer-style vault details with search and filters."""
from __future__ import annotations

import tkinter
import webbrowser
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from .. import icons
from . import theme as T
from .entry_dialog import EntryDialog
from .modal import confirm
from .widgets import Btn, Dropdown, Field, IconBtn, divider, fit_text, open_menu, style_scrollbar
from ..vault import SORT_OPTIONS, search_entries, sort_entries

MASK = "•" * 9
ROW_H = 34
PAGE = 100


def column_widths(total: float) -> tuple[int, int, int, int, int]:
    """Keep the command column fixed while sharing the remaining list width."""
    actions = 104
    available = max(460, int(total) - actions)
    name = int(available * .30)
    user = int(available * .25)
    url = int(available * .25)
    return name, user, url, available - name - user - url, actions


class EntryRow(ctk.CTkFrame):
    def __init__(self, master, entry: Dict[str, Any], actions: Dict[str, Any]):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0, height=ROW_H)
        self.pack_propagate(False)
        self.entry = entry
        self.act = actions
        self._revealed = False
        self._hover = False
        self._leave_job = None
        self._hide_job = None
        self._pos = None
        self._cw = None
        self._pw_width = 120
        self._base = T.SURFACE
        self._shown: Dict[int, str] = {}
        self._build()
        self._bind_hover(self)

    def _build(self) -> None:
        e = self.entry
        divider(self).pack(side="bottom", fill="x")
        self.cells = [ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=ROW_H - 1)
                      for _ in range(5)]
        for cell in self.cells:
            cell.pack(side="left", fill="y")
            cell.pack_propagate(False)

        ctk.CTkLabel(self.cells[0], text="", image=icons.entry_icon(e.get("title", ""), e.get("url", ""), 20),
                     width=24).pack(side="left", padx=(7, 3))
        self.title_lbl = ctk.CTkLabel(self.cells[0], text="", font=T.font(12, "bold"),
                                      text_color=T.TEXT, anchor="w")
        self.title_lbl.pack(side="left", fill="x", expand=True)
        self.user_val = ctk.CTkLabel(self.cells[1], text="", font=T.font(11),
                                     text_color=T.TEXT, anchor="w")
        self.user_val.pack(fill="x", padx=(8, 2))
        self.url_val = ctk.CTkLabel(self.cells[2], text="", font=T.font(11),
                                    text_color=T.TEXT_MUTED, anchor="w")
        self.url_val.pack(fill="x", padx=(8, 2))
        self.eye = IconBtn(self.cells[3], "eye", 14, 24, tooltip="Show / hide password",
                           command=self.toggle_reveal)
        self.eye.pack(side="right", padx=(0, 3))
        self.pass_val = ctk.CTkLabel(self.cells[3], text="", font=T.font(11),
                                     text_color=T.TEXT, anchor="w")
        self.pass_val.pack(side="left", fill="x", expand=True, padx=(8, 0))

        IconBtn(self.cells[4], "copy", 14, 24, tooltip="Copy username",
                command=lambda: self.act["copy_user"](e)).pack(side="left")
        IconBtn(self.cells[4], "clipboard", 14, 24, tooltip="Copy password",
                command=lambda: self.act["copy_pass"](e)).pack(side="left")
        IconBtn(self.cells[4], "pencil", 14, 24, tooltip="Edit",
                command=lambda: self.act["edit"](e)).pack(side="left")
        self.kebab = IconBtn(self.cells[4], "ellipsis-vertical", 14, 24,
                             tooltip="More actions", command=self._menu)
        self.kebab.pack(side="left")

        for cell in self.cells[:4]:
            cell.bind("<Double-Button-1>", lambda event: self.act["edit"](self.entry), add="+")
            for child in cell.winfo_children():
                if child is not self.eye:
                    child.bind("<Double-Button-1>", lambda event: self.act["edit"](self.entry), add="+")

    def _show(self, label: ctk.CTkLabel, text: str) -> None:
        if self._shown.get(id(label)) != text:
            self._shown[id(label)] = text
            label.configure(text=text)

    def set_width(self, logical_w: float) -> None:
        if self._cw is not None and abs(logical_w - self._cw) < 0.5:
            return
        self._cw = logical_w
        widths = column_widths(logical_w)
        for cell, width in zip(self.cells, widths):
            cell.configure(width=width)
        self._pw_width = widths[3]
        e = self.entry
        self._show(self.title_lbl, fit_text(e.get("title") or "Untitled", T.font(12, "bold"), widths[0] - 37))
        self._show(self.user_val, fit_text(e.get("username") or "—", T.font(11), widths[1] - 12))
        self._show(self.url_val, fit_text(e.get("url") or "—", T.font(11), widths[2] - 12))
        self._paint_password()

    def _paint_password(self) -> None:
        if self._revealed:
            self.pass_val.configure(font=T.font(11, mono=True))
            self._show(self.pass_val, fit_text(self.entry.get("password", ""), T.font(11, mono=True), self._pw_width - 36))
        else:
            self.pass_val.configure(font=T.font(11))
            self._show(self.pass_val, MASK if self.entry.get("password") else "—")

    def set_stripe(self, index: int) -> None:
        self._base = T.SURFACE if index % 2 == 0 else T.SURFACE_2
        if not self._hover:
            self.configure(fg_color=self._base)

    # ------------------------------------------------------------ actions
    def toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        self.eye.set_icon("eye-off" if self._revealed else "eye")
        self._paint_password()
        if self._hide_job:
            self.after_cancel(self._hide_job)
            self._hide_job = None
        if self._revealed:
            self._hide_job = self.after(15000, lambda: self.toggle_reveal() if self._revealed else None)

    def _menu(self) -> None:
        e, a = self.entry, self.act
        items = [
            {"label": "Copy username", "icon": "copy", "command": lambda: a["copy_user"](e)},
            {"label": "Copy password", "icon": "clipboard", "command": lambda: a["copy_pass"](e)},
            {"label": "Copy URL", "icon": "globe", "command": lambda: a["copy_url"](e)},
        ]
        if (e.get("url") or "").strip():
            items.append({"label": "Open website", "icon": "external-link", "command": lambda: a["open_url"](e)})
        items += [None,
                  {"label": "Edit", "icon": "pencil", "command": lambda: a["edit"](e)},
                  {"label": "Delete", "icon": "trash-2", "danger": True, "command": lambda: a["delete"](e)}]
        open_menu(self.kebab, items, align="right")

    # ------------------------------------------------------------ hover
    def _bind_hover(self, w) -> None:
        w.bind("<Enter>", self._enter, add="+")
        w.bind("<Leave>", self._leave, add="+")
        for c in w.winfo_children():
            self._bind_hover(c)

    def _enter(self, _e=None) -> None:
        if self._leave_job:
            self.after_cancel(self._leave_job)
            self._leave_job = None
        if not self._hover:
            self._hover = True
            self.configure(fg_color=T.ACCENT_SOFT)

    def _leave(self, _e=None) -> None:
        if self._leave_job:
            self.after_cancel(self._leave_job)
        self._leave_job = self.after(45, self._check_leave)

    def _check_leave(self) -> None:
        self._leave_job = None
        try:
            x, y = self.winfo_pointerxy()
            w = self.winfo_containing(x, y)
        except (tkinter.TclError, KeyError):
            w = None
        if w is not None and str(w).startswith(str(self)):
            return
        if self._hover:
            self._hover = False
            self.configure(fg_color=self._base)

    def destroy(self) -> None:
        for job in (self._leave_job, self._hide_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tkinter.TclError:
                    pass
        super().destroy()


class VaultPage(ctk.CTkFrame):
    def __init__(self, master, shell):
        super().__init__(master, fg_color="transparent")
        self.shell = shell
        self._cards: Dict[str, EntryRow] = {}
        self._sigs: Dict[str, tuple] = {}
        self._ordered: List[Dict[str, Any]] = []
        self._todo: List[str] = []
        self._chunk_job = None
        self._gen = 0
        self._limit = PAGE
        self._poll_job = None
        self._seen_version = -1
        self._search_job = None
        self._relayout_job = None
        self._last_layout_width = -1
        self._empty: Optional[ctk.CTkFrame] = None
        self._empty_has_any: Optional[bool] = None
        self._actions = {
            "copy_user": lambda e: shell.copy(e.get("username", ""), "Username", clear=False),
            "copy_pass": lambda e: shell.copy(e.get("password", ""), "Password"),
            "copy_url": lambda e: shell.copy(e.get("url", ""), "URL", clear=False),
            "open_url": self._open_url,
            "edit": self.edit_entry,
            "delete": self.delete_entry,
        }
        self._build()
        self.refresh()
        self.bind("<Configure>", self._on_configure, add="+")
        self._poll_job = self.after(300, self._poll)

    # ------------------------------------------------------------ build
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="My Vault", font=T.font(16, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=26, pady=(12, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=26, pady=(8, 12))
        Btn(bar, "Clear", "ghost", width=60, height=38, command=self.clear_filters).pack(side="right")
        self.filter_dd = Dropdown(bar, [("__all__", "All entries")], width=170, command=self._on_filter)
        self.filter_dd.pack(side="right", padx=(0, 8))
        self.sort_dd = Dropdown(bar, SORT_OPTIONS, value=self.shell.sort_key, width=170, command=self._on_sort)
        self.sort_dd.pack(side="right", padx=(0, 8))
        self.search = Field(bar, "Search entries...", icon="search", width=250)
        self.search.pack(side="right", padx=(0, 8))
        self.search.bind_key(self._on_search_key)
        self.search.set(self.shell.search_text)

        self.list_head = ctk.CTkFrame(self, fg_color=T.BUTTON_FACE, border_width=1,
                                      border_color=T.BORDER_STRONG, corner_radius=0, height=30)
        self.list_head.grid(row=2, column=0, sticky="ew", padx=(26, 20))
        self.list_head.pack_propagate(False)
        self.head_cells = []
        for text in ("Name", "Username", "Website", "Password", "Actions"):
            cell = ctk.CTkFrame(self.list_head, fg_color="transparent", corner_radius=0, height=28)
            cell.pack(side="left", fill="y")
            cell.pack_propagate(False)
            ctk.CTkLabel(cell, text=text, font=T.font(11, "bold"), text_color=T.TEXT_MUTED,
                         anchor="w").pack(fill="x", padx=8)
            self.head_cells.append(cell)

        self.body = ctk.CTkScrollableFrame(self, fg_color=T.SURFACE, corner_radius=0,
                                           border_width=1, border_color=T.BORDER_STRONG,
                                           scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.TEXT_FAINT)
        style_scrollbar(self.body)
        self.body.grid(row=3, column=0, sticky="nsew", padx=(26, 20), pady=(0, 10))
        self.body.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------ data
    def refresh(self) -> None:
        sh = self.shell
        self._seen_version = sh.data_version
        opts = [("__all__", "All entries"), ("__none__", "Ungrouped")] + [(g["id"], g["name"]) for g in sh.groups]
        if sh.filter_group not in [k for k, _ in opts]:
            sh.filter_group = "__all__"
        self.filter_dd.set_options(opts, sh.filter_group)
        self.sort_dd.set(sh.sort_key)
        self._apply()

    @staticmethod
    def _sig(e: Dict[str, Any]) -> tuple:
        return (e.get("title"), e.get("username"), e.get("password"), e.get("url"), e.get("notes"), e.get("group_id"), e.get("modified"))

    def _apply(self, reset: bool = False) -> None:
        if reset:
            self._limit = PAGE
        sh = self.shell
        pool = sh.entries
        if sh.filter_group == "__none__":
            pool = [e for e in pool if not e.get("group_id")]
        elif sh.filter_group != "__all__":
            pool = [e for e in pool if e.get("group_id") == sh.filter_group]
        self._ordered = sort_entries(search_entries(pool, sh.search_text), sh.sort_key)
        self._reconcile()

    def _reconcile(self) -> None:
        if self._chunk_job is not None:
            self.after_cancel(self._chunk_job)
            self._chunk_job = None
        self._gen += 1
        live = {e["id"]: e for e in self.shell.entries}
        for eid in list(self._cards):
            gone = eid not in live
            changed = not gone and self._sigs.get(eid) != self._sig(live[eid])
            if gone or changed:
                self._cards.pop(eid).destroy()
                self._sigs.pop(eid, None)
        visible = {e["id"] for e in self._ordered[:self._limit]}
        for eid, card in self._cards.items():
            if eid not in visible and card._pos is not None:
                card.grid_remove()
                card._pos = None
        self._todo = [e["id"] for e in self._ordered[:self._limit] if e["id"] not in self._cards]
        self._toggle_empty()
        self._layout()
        self._build_chunk(self._gen)

    def _build_chunk(self, gen: int) -> None:
        self._chunk_job = None
        if gen != self._gen or not self.winfo_exists():
            return
        by_id = {e["id"]: e for e in self._ordered[:self._limit]}
        for _ in range(12):
            if not self._todo:
                break
            eid = self._todo.pop(0)
            if eid in by_id and eid not in self._cards:
                c = EntryRow(self.body, by_id[eid], self._actions)
                self._cards[eid] = c
                self._sigs[eid] = self._sig(by_id[eid])
        self._layout()
        if self._todo:
            self._chunk_job = self.after(1, lambda: self._build_chunk(gen))

    # ------------------------------------------------------------ layout
    def _layout(self) -> None:
        """Keep the Explorer columns aligned while rows are built in chunks."""
        s = T.widget_scale(self)
        available = max(570.0, self.winfo_width() / s - 26 - 20 - 23)
        widths = column_widths(available)
        for cell, width in zip(self.head_cells, widths):
            cell.configure(width=width)
        for i, e in enumerate(self._ordered[:self._limit]):
            card = self._cards.get(e["id"])
            if card is None:
                continue
            pos = (i, 0)
            if card._pos != pos:
                card.grid(row=i, column=0, sticky="ew")
                card._pos = pos
            card.set_width(available)
            card.set_stripe(i)

    def _on_configure(self, _e=None) -> None:
        # Child redraws need not trigger an entire card-grid layout.
        width = self.winfo_width()
        if width == self._last_layout_width:
            return
        self._last_layout_width = width
        if self._relayout_job:
            self.after_cancel(self._relayout_job)
        self._relayout_job = self.after(70, self._layout)

    def _poll(self) -> None:
        """Load the next batch of rows when the user scrolls near the end."""
        try:
            if self.winfo_ismapped() and not self._todo and len(self._ordered) > self._limit:
                lo, hi = self.body._parent_canvas.yview()
                if hi > 0.82:
                    self._limit += PAGE
                    self._reconcile()
            self._poll_job = self.after(180, self._poll)
        except tkinter.TclError:
            self._poll_job = None

    def destroy(self) -> None:
        for name in ("_poll_job", "_search_job", "_relayout_job", "_chunk_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tkinter.TclError:
                    pass
                setattr(self, name, None)
        super().destroy()

    # ------------------------------------------------------------ empty state
    def _toggle_empty(self) -> None:
        if self._ordered:
            if self._empty is not None:
                self._empty.destroy()
                self._empty = None
                self._empty_has_any = None
            return
        has_any = bool(self.shell.entries)
        if self._empty is not None and self._empty_has_any == has_any:
            return
        if self._empty is not None:
            self._empty.destroy()
        f = ctk.CTkFrame(self.body, fg_color="transparent")
        f.grid(row=0, column=0, sticky="ew", pady=60)
        disc = ctk.CTkFrame(f, width=64, height=64, corner_radius=2, fg_color=T.ACCENT_SOFT)
        disc.pack()
        disc.pack_propagate(False)
        ctk.CTkLabel(disc, text="", image=icons.icon("search" if has_any else "lock", 28, T.ACCENT)).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(f, text="No matching entries" if has_any else "Your vault is empty", font=T.font(17, "bold"),
                     text_color=T.TEXT).pack(pady=(14, 2))
        ctk.CTkLabel(f, text="Try a different search or clear the filters." if has_any else "Add your first password to get started.",
                     font=T.font(13), text_color=T.TEXT_MUTED).pack()
        if has_any:
            Btn(f, "Clear filters", "secondary", width=130, command=self.clear_filters).pack(pady=(16, 0))
        else:
            Btn(f, "Add Entry", "primary", icon="plus", width=130, command=self.add_entry).pack(pady=(16, 0))
        self._empty = f
        self._empty_has_any = has_any

    # ------------------------------------------------------------ toolbar
    def _on_search_key(self, _e=None) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(120, self._search_now)

    def _search_now(self) -> None:
        self.shell.search_text = self.search.get()
        self._apply(reset=True)

    def _on_sort(self, key: str) -> None:
        self.shell.sort_key = key
        self._apply(reset=True)

    def _on_filter(self, key: str) -> None:
        self.shell.filter_group = key
        self._apply(reset=True)

    def clear_filters(self) -> None:
        self.search.set("")
        self.shell.search_text = ""
        self.shell.filter_group = "__all__"
        self.filter_dd.set("__all__")
        self._apply(reset=True)

    def focus_search(self) -> None:
        self.search.focus()

    # ------------------------------------------------------------ crud
    def add_entry(self) -> None:
        gid = self.shell.filter_group if self.shell.filter_group not in ("__all__", "__none__") else None
        dlg = EntryDialog(self.winfo_toplevel(), self.shell.groups, default_group_id=gid,
                          on_save=lambda fields, _id: self.shell.add_entry(fields))
        dlg.run()

    def edit_entry(self, entry: Dict[str, Any]) -> None:
        dlg = EntryDialog(self.winfo_toplevel(), self.shell.groups, existing=entry,
                          on_save=lambda fields, eid: self.shell.update_entry(eid, fields))
        dlg.run()

    def delete_entry(self, entry: Dict[str, Any]) -> None:
        name = entry.get("title") or "this entry"
        if confirm(self.winfo_toplevel(), "Delete entry?", f'"{name}" will be permanently removed from your vault. This cannot be undone.',
                   "Delete", danger=True):
            self.shell.delete_entry(entry["id"])

    @staticmethod
    def _open_url(entry: Dict[str, Any]) -> None:
        url = (entry.get("url") or "").strip()
        if not url:
            return
        if "://" not in url:
            url = "https://" + url
        if url.lower().startswith(("http://", "https://")):
            webbrowser.open(url)
