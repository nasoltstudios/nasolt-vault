"""Fresh master-password prompt for one quick-access request."""
from __future__ import annotations

import customtkinter as ctk

from . import theme as T
from .widgets import Btn, Field
from ..windows_focus import activate_window
from ..windows_shortcuts import active_monitor_work_area


class ReauthPrompt(ctk.CTkToplevel):
    def __init__(self, root, on_submit, on_cancel, destination="Vault Summon",
                 locked=False, on_open_full=None, on_hello=None):
        super().__init__(root, fg_color=T.BG)
        self.withdraw()
        # A decorated Tk child follows its withdrawn/iconified root on Windows.
        # This independent popup remains viewable when the vault lives in tray.
        self.overrideredirect(True)
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._on_open_full = on_open_full
        self._on_hello = on_hello
        frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0,
                             border_width=2, border_color=T.BORDER_STRONG)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text="Unlock Vault" if locked else "Confirm master password",
                     font=T.font(14, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=16, pady=(13, 2))
        ctk.CTkLabel(frame, text=f"Enter your master password to open {destination}.", font=T.font(11),
                     text_color=T.TEXT_MUTED).pack(anchor="w", padx=16)
        self.password = Field(frame, "Master password", password=True, width=315)
        self.password.pack(fill="x", padx=16, pady=(11, 5))
        self.password.bind_return(self.submit)
        self.error = ctk.CTkLabel(frame, text="", height=18, font=T.font(11),
                                  text_color=T.DANGER, anchor="w")
        self.error.pack(fill="x", padx=16)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(3, 10))
        Btn(buttons, "Cancel", "secondary", width=76, command=self.cancel).pack(side="right")
        self.confirm = Btn(buttons, "Continue", "primary", width=125,
                           command=self.submit)
        self.confirm.pack(side="right", padx=(0, 8))
        if on_hello is not None:
            Btn(buttons, "Windows Hello", "secondary", width=118,
                command=self.use_hello).pack(side="left")
        if locked and on_open_full is not None:
            Btn(buttons, "Open full Vault", "link", width=118,
                command=self.open_full).pack(side="left")
        self.bind("<Escape>", lambda _e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        root.update_idletasks()
        area = active_monitor_work_area((0, 0, root.winfo_screenwidth(), root.winfo_screenheight()))
        scale = T.window_scale(self)
        width, height = round(370 * scale), round(195 * scale)
        left, top, right, bottom = area
        x = max(left, min(right-width, left+(right-left-width)//2))
        y = max(top, min(bottom-height, top+(bottom-top-height)//2))
        self.geometry(f"370x195{x:+d}{y:+d}")
        self.bring_forward()

    def bring_forward(self):
        return activate_window(self, self.password)

    def show_error(self, message):
        self.error.configure(text=message, text_color=T.DANGER)
        self.confirm.set_enabled(True)
        self.bring_forward()

    def submit(self):
        value = self.password.get()
        self.password.set("")
        if not value:
            return
        self.confirm.set_enabled(False)
        self._on_submit(value)

    def cancel(self):
        callback, self._on_cancel = self._on_cancel, None
        if callback:
            callback()
        if self.winfo_exists():
            self.destroy()

    def use_hello(self):
        if self._on_hello is not None:
            self._on_hello()

    def show_status(self, message):
        self.error.configure(text=message, text_color=T.TEXT_MUTED)

    def open_full(self):
        callback, self._on_open_full = self._on_open_full, None
        if callback:
            callback()

    def close(self):
        self._on_cancel = None
        self._on_open_full = None
        self._on_hello = None
        self.destroy()
