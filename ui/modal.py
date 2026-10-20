"""modal.py — XP-style modal dialogs and confirm/prompt/alert helpers."""
from __future__ import annotations

import tkinter
from typing import Callable, Optional

import customtkinter as ctk

from ui import theme as T
from ui.anim import cancel_tree_after_jobs
from ui.widgets import Btn, Field, IconBtn, divider, titlebar


class Modal(ctk.CTkToplevel):
    open_modals: list = []

    def __init__(self, parent, title: str, width: int, height: int, closable: bool = True,
                 default_action: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(fg_color=T.BORDER_STRONG)          # 1px frame colour
        self._parent = parent.winfo_toplevel()
        self.result = None
        self._closing = False
        self._default_action = default_action
        self._focus_job = None
        self._dx = self._dy = 0

        shell = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        header = titlebar(shell, 32)
        header.pack(fill="x")
        self._title = ctk.CTkLabel(header, text=title, font=T.font(13, "bold"), text_color=T.TITLEBAR_TEXT, anchor="w")
        self._title.pack(side="left", padx=(13, 0))
        if closable:
            IconBtn(header, "x", 15, 23, color=T.TITLEBAR_TEXT, hover_color=T.TITLEBAR_TEXT,
                    base_bg=T.CLOSE_BG, hover_bg=T.CLOSE_HOVER, tooltip="Close",
                    command=self.cancel).pack(side="right", padx=(0, 6))
        divider(shell).pack(fill="x")
        self.body = ctk.CTkFrame(shell, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        bands = [w for w in header.winfo_children() if type(w) is tkinter.Frame]
        for w in (header, self._title, *bands):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        self.bind("<Escape>", lambda e: self.cancel() if closable else None)
        self.bind("<Return>", self._on_return)
        self._size = (width, height)

    # ---- lifecycle
    def present(self) -> None:
        """Position over the parent and grab input."""
        self.update_idletasks()
        s = T.window_scale(self)
        req_w, req_h = self._size
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(req_w, int(sw / s) - 40)
        h = min(req_h, int(sh / s) - 100)
        px, py = self._parent.winfo_rootx(), self._parent.winfo_rooty()
        pw, ph = self._parent.winfo_width(), self._parent.winfo_height()
        x = max(0, min(px + (pw - int(w * s)) // 2, sw - int(w * s)))
        y = max(0, min(py + (ph - int(h * s)) // 2, sh - int(h * s) - 40))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()
        self.lift()
        Modal.open_modals.append(self)
        self._focus_job = self.after(30, self._take_focus)

    def _take_focus(self) -> None:
        self._focus_job = None
        try:
            self.grab_set()
        except tkinter.TclError:
            pass
        try:
            self.focus_force()
        except tkinter.TclError:
            pass

    def cancel(self) -> None:
        self.close(None)

    def close(self, result=None) -> None:
        if self._closing:
            return
        self._closing = True
        self.result = result
        if self._focus_job is not None:
            try:
                self.after_cancel(self._focus_job)
            except tkinter.TclError:
                pass
            self._focus_job = None
        if self in Modal.open_modals:
            Modal.open_modals.remove(self)
        try:
            self.grab_release()
        except tkinter.TclError:
            pass

        try:
            self.destroy()
        except tkinter.TclError:
            pass

    def destroy(self) -> None:
        # CustomTkinter also schedules a delayed Windows icon callback on each
        # toplevel. Cancel this dialog's callbacks before Tk deletes its Tcl
        # commands; otherwise a quick close can emit a background Tcl error.
        cancel_tree_after_jobs(self)
        super().destroy()

    def run(self):
        self.present()
        self.wait_window(self)
        return self.result

    @staticmethod
    def close_all() -> None:
        for m in list(Modal.open_modals):
            try:
                m.destroy()
            except tkinter.TclError:
                pass
        Modal.open_modals.clear()

    # ---- keys / drag
    def _on_return(self, e) -> None:
        if isinstance(self.focus_get(), (tkinter.Text,)) or self._default_action is None:
            return
        self._default_action()

    def _drag_start(self, e) -> None:
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e) -> None:
        self.wm_geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")


# ------------------------------------------------------------------ helpers
def _footer(dlg: Modal) -> ctk.CTkFrame:
    row = ctk.CTkFrame(dlg.body, fg_color="transparent")
    row.pack(side="bottom", fill="x", padx=24, pady=(0, 20))
    return row


def confirm(parent, title: str, message: str, confirm_text: str = "Confirm", danger: bool = False,
            cancel_text: str = "Cancel") -> bool:
    dlg = Modal(parent, title, 440, 226, default_action=None)
    ctk.CTkLabel(dlg.body, text=message, font=T.font(13), text_color=T.TEXT_MUTED, justify="left", anchor="nw",
                 wraplength=390).pack(fill="x", padx=24, pady=(20, 0))
    footer = _footer(dlg)
    ok = Btn(footer, confirm_text, "danger" if danger else "primary", width=112,
             command=lambda: dlg.close(True))
    cancel = Btn(footer, cancel_text, "outline", width=96, command=dlg.cancel)
    cancel.pack(side="right")
    ok.pack(side="right", padx=(0, 10))
    dlg._default_action = lambda: dlg.close(True)
    return bool(dlg.run())


def alert(parent, title: str, message: str, button: str = "OK") -> None:
    dlg = Modal(parent, title, 460, 250, default_action=None)
    ctk.CTkLabel(dlg.body, text=message, font=T.font(13), text_color=T.TEXT_MUTED, justify="left", anchor="nw",
                 wraplength=410).pack(fill="x", padx=24, pady=(20, 0))
    footer = _footer(dlg)
    b = Btn(footer, button, "primary", width=96, command=dlg.cancel)
    b.pack(side="right")
    dlg._default_action = dlg.cancel
    dlg.run()


def prompt(parent, title: str, label: str, initial: str = "", placeholder: str = "", confirm_text: str = "Save",
           validate: Optional[Callable[[str], Optional[str]]] = None) -> Optional[str]:
    dlg = Modal(parent, title, 440, 250)
    ctk.CTkLabel(dlg.body, text=label, font=T.font(13), text_color=T.TEXT, anchor="w").pack(fill="x", padx=24, pady=(18, 6))
    field = Field(dlg.body, placeholder=placeholder)
    field.pack(fill="x", padx=24)
    err = ctk.CTkLabel(dlg.body, text="", font=T.font(12), text_color=T.DANGER, anchor="w")
    err.pack(fill="x", padx=24, pady=(6, 0))
    if initial:
        field.set(initial)

    def submit() -> None:
        value = field.get().strip()
        msg = validate(value) if validate else (None if value else "Please enter a name.")
        if msg:
            err.configure(text=msg)
            field.set_error(True)
            return
        dlg.close(value)

    footer = _footer(dlg)
    ok = Btn(footer, confirm_text, "primary", width=104, command=submit)
    cancel = Btn(footer, "Cancel", "outline", width=96, command=dlg.cancel)
    cancel.pack(side="right")
    ok.pack(side="right", padx=(0, 10))
    field.bind_return(submit)
    field.bind_key(lambda e: (err.configure(text=""), field.set_error(False)) if e.keysym not in ("Return",) else None)
    dlg._default_action = submit
    dlg.present()
    dlg.after(80, field.focus)
    dlg.wait_window(dlg)
    return dlg.result


def export_password_prompt(parent, *, confirm: bool) -> Optional[str]:
    """Ask for a portable export password without placing it in app state or logs."""
    dlg = Modal(parent, "Encrypt export" if confirm else "Decrypt export", 450, 344 if confirm else 258)
    message = ("Choose a password for this export. You will need it to import the file."
               if confirm else "Enter the password used when this export was created.")
    ctk.CTkLabel(dlg.body, text=message, font=T.font(12), text_color=T.TEXT,
                 anchor="w", wraplength=398).pack(fill="x", padx=24, pady=(17, 12))
    ctk.CTkLabel(dlg.body, text="Export password", font=T.font(12), text_color=T.TEXT,
                 anchor="w").pack(fill="x", padx=24, pady=(0, 5))
    field = Field(dlg.body, password=True)
    field.pack(fill="x", padx=24)
    again = None
    if confirm:
        ctk.CTkLabel(dlg.body, text="Confirm password", font=T.font(12), text_color=T.TEXT,
                     anchor="w").pack(fill="x", padx=24, pady=(13, 5))
        again = Field(dlg.body, password=True)
        again.pack(fill="x", padx=24)
    err = ctk.CTkLabel(dlg.body, text="", font=T.font(12), text_color=T.DANGER,
                       anchor="w")
    err.pack(fill="x", padx=24, pady=(7, 0))

    def submit() -> None:
        value = field.get()
        if not value:
            err.configure(text="Enter the export password.")
            field.set_error(True)
        elif confirm and len(value) < 12:
            err.configure(text="Use at least 12 characters for this export password.")
            field.set_error(True)
        elif again is not None and value != again.get():
            err.configure(text="Passwords do not match.")
            again.set_error(True)
        else:
            dlg.close(value)

    footer = _footer(dlg)
    ok = Btn(footer, "Encrypt" if confirm else "Decrypt", "primary", width=100, command=submit)
    cancel = Btn(footer, "Cancel", "outline", width=96, command=dlg.cancel)
    cancel.pack(side="right")
    ok.pack(side="right", padx=(0, 10))
    field.bind_return(submit)
    if again is not None:
        again.bind_return(submit)
    dlg._default_action = submit
    dlg.present()
    dlg.after(80, field.focus)
    dlg.wait_window(dlg)
    return dlg.result


def master_password_prompt(parent, title: str = "Confirm master password") -> Optional[str]:
    """Collect a master password for an explicit settings action, without logging it."""
    dlg = Modal(parent, title, 440, 245)
    ctk.CTkLabel(dlg.body, text="Enter your current master password.", font=T.font(12),
                 text_color=T.TEXT, anchor="w").pack(fill="x", padx=24, pady=(18, 7))
    field = Field(dlg.body, password=True)
    field.pack(fill="x", padx=24)

    def submit() -> None:
        value = field.get()
        field.set("")
        if value:
            dlg.close(value)

    footer = _footer(dlg)
    cancel = Btn(footer, "Cancel", "outline", width=96, command=dlg.cancel)
    ok = Btn(footer, "Continue", "primary", width=104, command=submit)
    cancel.pack(side="right")
    ok.pack(side="right", padx=(0, 10))
    field.bind_return(submit)
    dlg._default_action = submit
    dlg.present()
    dlg.after(80, field.focus)
    dlg.wait_window(dlg)
    return dlg.result
