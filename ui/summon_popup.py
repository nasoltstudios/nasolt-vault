"""Small authenticated quick-search window. It never receives password values."""
from __future__ import annotations

import customtkinter as ctk

import icons
from ui import theme as T
from windows_shortcuts import active_monitor_work_area


class SummonPopup(ctk.CTkToplevel):
    WIDTH, HEIGHT = 390, 385

    def __init__(self, root, search, copy, on_close, on_activity, timeout_seconds: int):
        super().__init__(root, fg_color=T.SURFACE)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._search = search
        self._copy = copy
        self._on_close = on_close
        self._on_activity = on_activity
        self._selected_id = None
        self._rows = []
        self._timeout_ms = timeout_seconds * 1000
        self._timeout_job = None
        self.bind("<Escape>", lambda _e: self.close(), add="+")
        self.bind("<Motion>", self._touch, add="+")
        self.bind("<Key>", self._touch, add="+")

        frame = ctk.CTkFrame(self, fg_color=T.SURFACE, border_color=T.BORDER_STRONG,
                             border_width=2, corner_radius=0)
        frame.pack(fill="both", expand=True)
        heading = ctk.CTkFrame(frame, fg_color=T.BUTTON_FACE, corner_radius=0, height=32)
        heading.pack(fill="x")
        heading.pack_propagate(False)
        ctk.CTkLabel(heading, text="Vault Summon", font=T.font(13, "bold"),
                     text_color=T.TEXT).pack(side="left", padx=12)
        ctk.CTkButton(heading, text="×", width=28, height=26, corner_radius=0,
                      fg_color="transparent", hover_color=T.SURFACE_2,
                      text_color=T.TEXT, command=self.close).pack(side="right", padx=3)

        self.query = ctk.CTkEntry(frame, placeholder_text="Search accounts", width=355,
                                  height=34, corner_radius=0, fg_color=T.INPUT,
                                  border_color=T.BORDER_STRONG, text_color=T.TEXT,
                                  font=T.font(13))
        self.query.pack(fill="x", padx=12, pady=(12, 8))
        self.query.bind("<KeyRelease>", self._on_query, add="+")
        self.query.bind("<Down>", self._move_down, add="+")
        self.query.bind("<Return>", self._select_first, add="+")
        self.results = ctk.CTkScrollableFrame(frame, fg_color=T.SURFACE,
                                              corner_radius=0, height=240)
        self.results.pack(fill="both", expand=True, padx=10)
        self.info = ctk.CTkLabel(frame, text="Select an account to copy a field.",
                                 font=T.font(11), text_color=T.TEXT_MUTED, anchor="w")
        self.info.pack(fill="x", padx=13, pady=(3, 0))
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(4, 9))
        self.username_button = ctk.CTkButton(actions, text="Copy username", height=30,
                                              command=lambda: self._copy_selected("username"),
                                              state="disabled", corner_radius=1)
        self.username_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.password_button = ctk.CTkButton(actions, text="Copy password", height=30,
                                              command=lambda: self._copy_selected("password"),
                                              state="disabled", corner_radius=1)
        self.password_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._refresh()
        root.update_idletasks()
        fallback = (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
        left, top, right, bottom = active_monitor_work_area(fallback)
        scale = T.window_scale(self)
        physical_w, physical_h = int(self.WIDTH*scale), int(self.HEIGHT*scale)
        x = max(left, min(right-physical_w, left+(right-left-physical_w)//2))
        y = max(top, min(bottom-physical_h, top+(bottom-top-physical_h)//3))
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}{x:+d}{y:+d}")
        self.deiconify()
        self.lift()
        self.focus_force()
        self.query.focus_set()
        self._touch()

    def _touch(self, _event=None):
        self._on_activity()
        if self._timeout_job:
            self.after_cancel(self._timeout_job)
        self._timeout_job = self.after(self._timeout_ms, self.close)

    def _on_query(self, event):
        if event.keysym not in ("Down", "Up", "Return", "Escape"):
            self._refresh()
        self._touch()

    def _refresh(self):
        self._selected_id = None
        self.username_button.configure(state="disabled")
        self.password_button.configure(state="disabled")
        for child in self.results.winfo_children():
            child.destroy()
        self._rows = self._search(self.query.get())[:30]
        if not self._rows:
            ctk.CTkLabel(self.results, text="No matching accounts", font=T.font(12),
                         text_color=T.TEXT_MUTED).pack(pady=18)
        for index, row in enumerate(self._rows):
            title = row["title"] if len(row["title"]) <= 38 else row["title"][:37] + "…"
            username = row["username"] if len(row["username"]) <= 45 else row["username"][:44] + "…"
            item = ctk.CTkButton(self.results, text=f"  {title}\n  {username}",
                                 image=icons.entry_icon(row["title"], row["url"], size=25),
                                 compound="left", anchor="w", height=47, corner_radius=1,
                                 fg_color="transparent", hover_color=T.SURFACE_2,
                                 text_color=T.TEXT, font=T.font(12),
                                 command=lambda i=index: self._select(i))
            item.pack(fill="x", pady=1)
            item.bind("<Return>", lambda _e, i=index: (self._select(i), "break")[1], add="+")
            item.bind("<Down>", lambda _e, i=index: self._focus_row(i+1), add="+")
            item.bind("<Up>", lambda _e, i=index: self._focus_row(i-1), add="+")
        self.info.configure(text=f"{len(self._rows)} matching account(s)" if self._rows else "No matching accounts")

    def _focus_row(self, index):
        if self._rows:
            self.results.winfo_children()[index % len(self._rows)].focus_set()
        return "break"

    def _move_down(self, _event):
        return self._focus_row(0)

    def _select_first(self, _event):
        if self._rows:
            self._select(0)
        return "break"

    def _select(self, index):
        if index >= len(self._rows):
            return
        row = self._rows[index]
        self._selected_id = row["id"]
        self.info.configure(text=row["title"])
        self.username_button.configure(state="normal")
        self.password_button.configure(state="normal")
        self.password_button.focus_set()
        self._touch()

    def _copy_selected(self, field):
        entry_id = self._selected_id
        if entry_id is None:
            return
        if self._copy(entry_id, field) and field == "password":
            self.close()
        else:
            self._touch()

    def close(self):
        if self._timeout_job:
            self.after_cancel(self._timeout_job)
            self._timeout_job = None
        self._rows = []
        self._selected_id = None
        callback, self._on_close = self._on_close, None
        if callback:
            callback()
        self.destroy()
