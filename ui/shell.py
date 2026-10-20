"""shell.py — the unlocked app: sidebar, page stack, auto-lock, and every vault operation."""
from __future__ import annotations

import logging
import math
import tkinter
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import app_settings
import clipboard
import export as export_mod
import icons
import vault
from ui import theme as T
from ui.anim import cancel, tween_color
from ui.generator_page import GeneratorPage
from ui.groups_page import GroupsPage
from ui.lockout_lab_page import LockoutLabPage
from ui.modal import Modal
from ui.settings_page import SettingsPage
from ui.transfer_page import TransferPage
from ui.vault_page import VaultPage
from ui.widgets import Btn, Popup, divider, hand, open_menu, titlebar

log = logging.getLogger("nasolt.shell")

NAV = [("vault", "My Vault", "house"), ("groups", "Groups", "folder"), ("generator", "Password Generator", "key-round"),
       ("lockout_lab", "Lockout Lab", "shield-check"),
       ("transfer", "Import / Export", "arrow-left-right"), ("settings", "Settings", "settings")]
NAV_COLORS = {"vault": T.ACCENT, "groups": T.FOLDER, "generator": T.WARNING,
              "lockout_lab": T.SUCCESS, "transfer": T.ACCENT, "settings": T.TEXT_FAINT}
PAGES = {"vault": VaultPage, "groups": GroupsPage, "generator": GeneratorPage,
         "lockout_lab": LockoutLabPage, "transfer": TransferPage, "settings": SettingsPage}


class NavItem(ctk.CTkFrame):
    def __init__(self, master, key: str, label: str, icon_name: str, on_click):
        super().__init__(master, fg_color="transparent", corner_radius=1, height=32)
        self.pack_propagate(False)
        self.key, self._icon_name, self._active, self._hover = key, icon_name, False, False
        self._icon_color = NAV_COLORS.get(key, T.TEXT_MUTED)
        self.bar = ctk.CTkFrame(self, width=4, corner_radius=0, fg_color=T.ACCENT_LINE)
        self.icon = ctk.CTkLabel(self, text="", image=icons.icon(icon_name, 16, self._icon_color), width=22)
        self.icon.pack(side="left", padx=(8, 5))
        self.text = ctk.CTkLabel(self, text=label, font=T.font(12), text_color=T.ACCENT_HOVER, anchor="w")
        self.text.pack(side="left", fill="x", expand=True)
        for w in (self, self.icon, self.text):
            w.bind("<Button-1>", lambda e: on_click(key), add="+")
            w.bind("<Enter>", lambda e: self._on_hover(True), add="+")
            w.bind("<Leave>", lambda e: self._on_hover(False), add="+")
            hand(w)

    def _on_hover(self, on: bool) -> None:
        if self._active:
            return
        a, b = T.resolve(T.SURFACE), T.resolve(T.SURFACE_2)
        tween_color(self, "fg_color", a if on else b, b if on else a, 110, final=T.SURFACE_2 if on else "transparent", key="bg")
        self.text.configure(text_color=T.ACCENT if on else T.ACCENT_HOVER)

    def set_active(self, on: bool) -> None:
        cancel(self, "bg")
        self._active = on
        self.configure(fg_color=T.ACCENT_SOFT if on else "transparent",
                       border_width=0)
        self.icon.configure(image=icons.icon(self._icon_name, 16, self._icon_color))
        self.text.configure(text_color=T.TEXT if on else T.ACCENT_HOVER,
                            font=T.font(12, "bold" if on else "normal"))
        if on:
            self.bar.place(x=0, y=0, relheight=1)
        else:
            self.bar.place_forget()


class Shell(ctk.CTkFrame):
    def __init__(self, master, app, session: vault.VaultSession, entries: List[Dict[str, Any]], groups: List[Dict[str, Any]]):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app, self.session = app, session
        self.entries, self.groups = entries, groups
        self.data_version = 0
        self.filter_group = "__all__"
        self.sort_key = "title"
        self.search_text = ""
        self.autolock_minutes = int(app_settings.get("autolock_minutes", 15) or 15)
        self.pages: Dict[str, ctk.CTkFrame] = {}
        self.current: Optional[str] = None
        self._tick_job = None
        self._status_text = ""
        self._build()
        self.navigate("vault")
        self._tick()

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        menu = ctk.CTkFrame(self, fg_color=T.BUTTON_FACE, corner_radius=0, height=31)
        menu.pack(side="top", fill="x")
        menu.pack_propagate(False)
        self.menu_buttons = {}
        self._menu_button(menu, "File", [
            {"label": "Lock vault", "icon": "lock", "command": self.lock},
            {"label": "Import / Export", "icon": "arrow-left-right", "command": lambda: self.navigate("transfer")},
            None,
            {"label": "Exit", "icon": "x", "command": self.app.close},
        ])
        self._menu_button(menu, "Edit", [
            {"label": "New entry", "icon": "plus", "command": self.new_entry},
            {"label": "Find entries", "icon": "search", "command": self.focus_search},
        ])
        self._menu_button(menu, "View", [
            {"label": label, "icon": icon_name, "command": lambda k=key: self.navigate(k)}
            for key, label, icon_name in NAV
        ])
        self._menu_button(menu, "Tools", [
            {"label": "Password Generator", "icon": "key-round", "command": lambda: self.navigate("generator")},
            {"label": "Lockout Lab", "icon": "shield-check", "command": lambda: self.navigate("lockout_lab")},
        ])
        self.add_entry_button = Btn(menu, "Add Entry", "secondary", icon="plus",
                                    width=112, height=26, command=self.new_entry)
        self.add_entry_button.pack(side="right", padx=8, pady=2)
        divider(self, color=T.BORDER_STRONG).pack(side="top", fill="x")

        status = ctk.CTkFrame(self, fg_color=T.BUTTON_FACE, corner_radius=0, height=27)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        divider(status, color=T.BORDER_STRONG).pack(fill="x")
        self.status_lbl = ctk.CTkLabel(status, text="", font=T.font(11),
                                        text_color=T.TEXT_MUTED, anchor="w")
        self.status_lbl.pack(fill="x", padx=12)

        workspace = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        workspace.pack(side="top", fill="both", expand=True)
        side = ctk.CTkFrame(workspace, width=200, fg_color=T.SIDEBAR, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        divider(workspace, vertical=True).pack(side="left", fill="y")

        tasks = ctk.CTkFrame(side, fg_color=T.SURFACE, border_width=1,
                             border_color=T.BORDER_STRONG, corner_radius=2)
        tasks.pack(fill="x", padx=10, pady=(12, 0))
        tasks_head = titlebar(tasks, 36)
        tasks_head.pack(fill="x")
        ctk.CTkLabel(tasks_head, text="Vault Tasks", font=T.font(12, "bold"),
                     text_color=T.TITLEBAR_TEXT, anchor="w").pack(fill="x", padx=12)
        nav = ctk.CTkFrame(tasks, fg_color="transparent")
        nav.pack(fill="x", padx=4, pady=5)
        self.nav_items: Dict[str, NavItem] = {}
        for key, label, ic in NAV:
            item = NavItem(nav, key, label, ic, self.navigate)
            item.pack(fill="x", pady=1)
            self.nav_items[key] = item

        foot = ctk.CTkFrame(side, fg_color=T.SURFACE, border_width=1,
                            border_color=T.BORDER_STRONG, corner_radius=2)
        foot.pack(side="bottom", fill="x", padx=10, pady=10)
        st = ctk.CTkFrame(foot, fg_color="transparent")
        st.pack(fill="x", padx=10, pady=10)
        dot = ctk.CTkFrame(st, width=24, height=24, corner_radius=2, fg_color=T.SUCCESS_SOFT)
        dot.pack(side="left")
        dot.pack_propagate(False)
        ctk.CTkLabel(dot, text="", image=icons.icon("shield-check", 14, T.SUCCESS)).place(relx=0.5, rely=0.5, anchor="center")
        txt = ctk.CTkFrame(st, fg_color="transparent")
        txt.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(txt, text="Vault Unlocked", font=T.font(12, "bold"), text_color=T.TEXT, anchor="w").pack(anchor="w")
        self.lock_lbl = ctk.CTkLabel(txt, text="", font=T.font(11), text_color=T.TEXT_MUTED, anchor="w")
        self.lock_lbl.pack(anchor="w")
        Btn(foot, "Lock vault", "outline", icon="lock", anchor="w", height=30,
            command=self.lock).pack(fill="x", padx=10, pady=(0, 10))

        self.content = ctk.CTkFrame(workspace, fg_color=T.BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self.page_host = ctk.CTkFrame(self.content, fg_color=T.BG, corner_radius=0)
        self.page_host.pack(side="top", fill="both", expand=True)

    def _menu_button(self, parent, label: str, items: list) -> None:
        button = ctk.CTkButton(parent, text=label, width=max(48, len(label) * 10 + 18), height=29,
                               fg_color="transparent", hover_color=T.ACCENT_SOFT,
                               text_color=T.TEXT, font=T.font(12), corner_radius=0)
        button.configure(command=lambda: open_menu(button, items, align="left"))
        button.pack(side="left")
        hand(button)
        self.menu_buttons[label.lower()] = (button, items)

    def open_app_menu(self, label: str) -> None:
        menu = self.menu_buttons.get(label.lower())
        if menu is not None:
            button, items = menu
            open_menu(button, items, align="left")

    def _update_status(self) -> None:
        count = len(self.entries)
        self.status_lbl.configure(text=f"{count} {'item' if count == 1 else 'items'}  |  {dict((k, v) for k, v, _ in NAV).get(self.current, 'My Vault')}")

    # ------------------------------------------------------------ navigation
    def navigate(self, key: str) -> None:
        Popup.close_current()
        if key == self.current:
            return
        prev = self.pages.get(self.current) if self.current else None
        if prev is not None:
            prev.place_forget()
        page = self.pages.get(key)
        if page is None:
            page = PAGES[key](self.page_host, self)
            self.pages[key] = page
        elif getattr(page, "_seen_version", self.data_version) != self.data_version and hasattr(page, "refresh"):
            page.refresh()
        page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.current = key
        for k, item in self.nav_items.items():
            item.set_active(k == key)
        self._update_status()

    def open_group(self, group_id: Optional[str]) -> None:
        self.filter_group = "__none__" if group_id is None else group_id
        self.search_text = ""
        self.navigate("vault")
        page = self.pages["vault"]
        page.search.set("")
        page.refresh()

    def _refresh_current(self) -> None:
        self.data_version += 1
        self._update_status()
        page = self.pages.get(self.current) if self.current else None
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    # ------------------------------------------------------------ feedback
    def notify(self, title: str, message: str = "", kind: str = "success") -> None:
        self.app.toasts.show(title, message, kind)

    def copy(self, text: str, label: str, clear: bool = True) -> None:
        if not text:
            self.notify("Nothing to copy", f"This entry has no {label.lower()}.", "info")
            return
        ok = clipboard.copy_to_clipboard(text) if clear else clipboard.copy_without_clear(text)
        if not ok:
            self.notify("Couldn't copy", "The clipboard is unavailable right now.", "error")
            return
        self.notify(f"Copied {label}", f"{label} copied to clipboard." + (f" Clears in {clipboard.COPY_TIMEOUT_SECONDS}s." if clear else ""), "copy")

    # ------------------------------------------------------------ persistence
    def _persist(self) -> bool:
        try:
            self.session.save(self.entries, self.groups)
            return True
        except vault.VaultConflictError:
            self.notify("Vault changed outside this app", "Your edit was not saved. Close this vault and inspect the encrypted files before retrying.", "error")
            return False
        except Exception as e:  # noqa: BLE001
            log.error("save failed (%s)", type(e).__name__)
            self.notify("Couldn't save your vault", "No changes were written. Check the data folder and available disk space.", "error")
            return False

    def add_entry(self, fields: Dict[str, Any]) -> bool:
        entry = vault._default_entry(**fields)
        self.entries.append(entry)
        if not self._persist():
            self.entries.remove(entry)
            return False
        self.notify("Entry added", f"{entry['title']} has been added to your vault.")
        self._refresh_current()
        return True

    def update_entry(self, entry_id: str, fields: Dict[str, Any]) -> bool:
        old = vault.get_entry_by_id(self.entries, entry_id)
        if old is None:
            return False
        snapshot = dict(old)
        vault.update_entry(self.entries, entry_id, **fields)
        if not self._persist():
            old.clear()
            old.update(snapshot)
            return False
        self.notify("Entry updated", f"{fields.get('title', old.get('title', 'Entry'))} was saved.")
        self._refresh_current()
        return True

    def delete_entry(self, entry_id: str) -> None:
        idx = next((i for i, e in enumerate(self.entries) if e["id"] == entry_id), None)
        if idx is None:
            return
        removed = self.entries.pop(idx)
        if not self._persist():
            self.entries.insert(idx, removed)
            return
        self.notify("Entry deleted", f"{removed.get('title') or 'Entry'} was removed from your vault.")
        self._refresh_current()

    def add_group(self, name: str) -> Optional[Dict[str, Any]]:
        g = vault.add_group(self.groups, name)
        if not self._persist():
            self.groups.remove(g)
            return None
        self.notify("Group created", f"{name} is ready to use.")
        self._refresh_current()
        return g

    def rename_group(self, group_id: str, name: str) -> None:
        g = vault.get_group_by_id(self.groups, group_id)
        if g is None:
            return
        old = g["name"]
        vault.rename_group(self.groups, group_id, name)
        if not self._persist():
            g["name"] = old
            return
        self.notify("Group renamed", f"{old} → {name}")
        self._refresh_current()

    def delete_group(self, group_id: str) -> None:
        g = vault.get_group_by_id(self.groups, group_id)
        if g is None:
            return
        members = [e for e in self.entries if e.get("group_id") == group_id]
        idx = self.groups.index(g)
        vault.delete_group(self.groups, self.entries, group_id)
        if not self._persist():
            self.groups.insert(idx, g)
            for e in members:
                e["group_id"] = group_id
            return
        if self.filter_group == group_id:
            self.filter_group = "__all__"
        self.notify("Group deleted", f"{g['name']} was removed. Its entries are now Ungrouped.")
        self._refresh_current()

    def import_rows(self, rows: List[Dict[str, str]]) -> Optional[export_mod.ImportResult]:
        before_e, before_g = len(self.entries), len(self.groups)
        res = export_mod.merge_import(self.entries, self.groups, rows)
        if not self._persist():
            del self.entries[before_e:]
            del self.groups[before_g:]
            return None
        self._refresh_current()
        return res

    # ------------------------------------------------------------ settings
    def set_autolock(self, minutes: int) -> None:
        self.autolock_minutes = minutes
        app_settings.set_value("autolock_minutes", minutes)
        self._status_text = ""

    # ------------------------------------------------------------ auto-lock
    def _tick(self) -> None:
        try:
            remaining = self.autolock_minutes * 60 - self.app.idle_seconds()
            if remaining <= 0:
                self.lock("Locked after inactivity.")
                return
            text = f"Auto-lock in {math.ceil(remaining / 60)} minute{'s' if math.ceil(remaining / 60) != 1 else ''}" if remaining > 90 \
                else f"Auto-lock in {int(remaining)} seconds"
            if text != self._status_text:
                self._status_text = text
                self.lock_lbl.configure(text=text)
            self._tick_job = self.after(1000, self._tick)
        except Exception as exc:
            self._tick_job = None
            try:
                alive = bool(self.winfo_exists())
            except tkinter.TclError:
                alive = False
            if alive:
                log.error("auto-lock timer failed (%s)", type(exc).__name__)
                self.lock("Vault locked after a timer error.")

    def lock(self, message: Optional[str] = None) -> None:
        Popup.close_current()
        Modal.close_all()
        clipboard.clear_now()
        self.app.show_login(message)

    def destroy(self) -> None:
        if self._tick_job:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        super().destroy()

    # ------------------------------------------------------------ shortcuts
    def new_entry(self) -> None:
        self.navigate("vault")
        self.pages["vault"].add_entry()

    def focus_search(self) -> None:
        self.navigate("vault")
        self.pages["vault"].focus_search()
