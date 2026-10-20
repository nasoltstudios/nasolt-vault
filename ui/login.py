"""login.py — XP-style unlock / create-vault screen."""
from __future__ import annotations

import logging
import math
import threading
from typing import Callable, Optional

import customtkinter as ctk

import icons
import vault
from generators import estimate_strength
from ui import theme as T
from ui.anim import animate, cancel_owned_after_jobs
from ui.modal import alert, confirm
from ui.widgets import Btn, Field, StrengthMeter, divider, groupbox, titlebar

log = logging.getLogger("nasolt.login")
MIN_LENGTH = 8


class LoginView(ctk.CTkFrame):
    def __init__(self, master, app, message: Optional[str] = None):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.mode = "unlock" if vault.vault_exists() else "create"
        self._busy = False
        self._busy_job = None
        self._focus_job = None
        self._active_worker = None
        self._message = message
        self._build()
        self._show_form()

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        body = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        side = ctk.CTkFrame(body, width=200, fg_color=T.SIDEBAR, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        divider(body, vertical=True).pack(side="left", fill="y")
        right = ctk.CTkFrame(body, fg_color=T.BG, corner_radius=0)
        right.pack(side="left", fill="both", expand=True)
        brand = ctk.CTkFrame(right, fg_color="transparent")
        brand.pack(anchor="nw", padx=28, pady=(18, 0))
        ctk.CTkLabel(brand, text="", image=icons.app_logo(34), width=34,
                     height=34).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(brand, text="Nasolt Vault", font=T.font(17, "bold"),
                     text_color=T.TEXT).pack(side="left")

        tasks = ctk.CTkFrame(side, fg_color=T.SURFACE, border_width=1,
                             border_color=T.BORDER_STRONG, corner_radius=2)
        tasks.pack(fill="x", padx=10, pady=(18, 0))
        task_head = titlebar(tasks, 34)
        task_head.pack(fill="x")
        ctk.CTkLabel(task_head, text="Vault Tasks", font=T.font(12, "bold"),
                     text_color=T.TITLEBAR_TEXT, anchor="w").pack(fill="x", padx=12)
        self.btn_unlock = Btn(tasks, "Unlock Vault", "primary", width=164, height=28,
                              anchor="w", command=lambda: self._set_mode("unlock"))
        self.btn_unlock.pack(fill="x", padx=8, pady=(10, 4))
        self.btn_create = Btn(tasks, "Create New Vault", "secondary", width=164,
                              height=28, anchor="w", command=self._choose_create)
        self.btn_create.pack(fill="x", padx=8, pady=(4, 10))
        Btn(side, "Forgot your password?", "link", width=176, height=28,
            size=12, anchor="w", command=self._forgot).pack(anchor="w", padx=14, pady=(12, 0))

        form_box, self.form = groupbox(right, "Vault access")
        form_box.place(relx=0.5, rely=0.5, anchor="center")

    def _style_buttons(self) -> None:
        exists = vault.vault_exists()
        active_unlock = self.mode == "unlock"
        for btn, primary in ((self.btn_unlock, active_unlock), (self.btn_create, not active_unlock)):
            v = "primary" if primary else "secondary"
            st = btn.STYLES[v]
            btn._st, btn._variant = st, v
            btn._normal_border_width = 2 if primary else 1
            btn.configure(fg_color=st["fg"], text_color=st["text"], border_width=btn._normal_border_width,
                          border_color=st["border"] or T.BORDER, font=T.font(13, "bold" if primary else "normal"))
            btn._sync_bevel()
        self.btn_unlock.set_enabled(exists)

    def _set_mode(self, mode: str) -> None:
        if self._busy:
            return
        if mode == "unlock" and not vault.vault_exists():
            return
        self.mode = mode
        self._show_form()

    def _choose_create(self) -> None:
        if self._busy:
            return
        if vault.vault_exists() and self.mode != "create":
            ok = confirm(self.winfo_toplevel(), "Create a new vault?",
                         "A new, empty vault will be created with a new master password. Your current vault file is not deleted — "
                         "it is kept next to the new one as a backup (vault.enc.replaced-…), but this app will open the new vault.",
                         "Create new vault", danger=True)
            if not ok:
                return
        self._set_mode("create")

    def _forgot(self) -> None:
        alert(self.winfo_toplevel(), "Forgot your password?",
              "Nasolt Vault is fully offline and your master password is never stored anywhere, so it can't be reset or recovered — "
              "that is what keeps your data safe.\n\nIf you remember it, choose Unlock Vault. Otherwise you can create a new vault; "
              "your old encrypted vault stays on disk as a backup in case you remember the password later.")

    # ------------------------------------------------------------ forms
    def _label(self, text: str, pady=(10, 5)) -> None:
        ctk.CTkLabel(self.form, text=text, font=T.font(12), text_color=T.TEXT, anchor="w").pack(fill="x", pady=pady)

    def _show_form(self) -> None:
        if self._focus_job is not None:
            self.after_cancel(self._focus_job)
            self._focus_job = None
        for w in self.form.winfo_children():
            w.destroy()
        self._style_buttons()
        creating = self.mode == "create"
        ctk.CTkLabel(self.form, text="Create New Vault" if creating else "Unlock Vault", font=T.font(17, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(self.form, text="Set a strong master password to protect your vault." if creating else
                     "Enter your master password to open your vault.", font=T.font(12), text_color=T.TEXT_MUTED, anchor="w").pack(fill="x", pady=(2, 2))

        self._label("Master Password", (10, 5))
        self.wrap = ctk.CTkFrame(self.form, fg_color="transparent")
        self.wrap.pack(fill="x")
        self.f_pw = Field(self.wrap, "Enter your master password", password=True, width=400, height=34)
        self.f_pw.pack(fill="x")
        self.f_pw.bind_return(self._submit)

        if creating:
            self._label("Confirm Password")
            self.f_confirm = Field(self.form, "Re-enter your master password", password=True, width=400, height=34)
            self.f_confirm.pack(fill="x")
            self.f_confirm.bind_return(self._submit)
            self._label("Password Strength", (10, 5))
            self.meter = StrengthMeter(self.form, segments=6, label_width=84)
            self.meter.pack(fill="x")
            self.f_pw.bind_key(self._on_key)

        self.err = ctk.CTkLabel(self.form, text=self._message or "", font=T.font(12), height=18,
                                text_color=T.TEXT_MUTED if self._message else T.DANGER, anchor="w", wraplength=400, justify="left")
        self.err.pack(fill="x", pady=(6, 0))
        self._message = None
        self.submit = Btn(self.form, "Create Vault" if creating else "Unlock", "primary", width=140,
                          height=32, command=self._submit)
        self.submit.pack(anchor="e", pady=(8, 0))
        def focus_password() -> None:
            self._focus_job = None
            if self.f_pw.winfo_exists():
                self.f_pw.focus()

        self._focus_job = self.after(120, focus_password)

    def destroy(self) -> None:
        cancel_owned_after_jobs(self)
        self._focus_job = None
        self._busy_job = None
        super().destroy()

    def _on_key(self, _e=None) -> None:
        pw = self.f_pw.get()
        if not pw:
            self.meter.set(0, "")
            return
        r = estimate_strength(pw)
        self.meter.set(r["entropy_bits"], r["label"])

    def _error(self, text: str, field: Optional[Field] = None) -> None:
        self.err.configure(text=text, text_color=T.DANGER)
        if field is not None:
            field.set_error(True)
            self.after(1800, lambda: field.set_error(False) if field.winfo_exists() else None)

    def _shake(self) -> None:
        animate(self.wrap, "shake", 380, lambda t: self.wrap.pack_configure(
            padx=(max(0, int(9 * math.sin(t * math.pi * 5) * (1 - t))), max(0, int(-9 * math.sin(t * math.pi * 5) * (1 - t))))))

    # ------------------------------------------------------------ submit
    def _submit(self) -> None:
        if self._busy:
            return
        pw = self.f_pw.get()
        if self.mode == "unlock":
            if not pw:
                return self._error("Enter your master password.", self.f_pw)
            self._busy_start("Unlocking")
            self._bg(lambda: self.app.session.open(pw), self._unlocked)
        else:
            if len(pw) < MIN_LENGTH:
                return self._error(f"Use at least {MIN_LENGTH} characters.", self.f_pw)
            if pw != self.f_confirm.get():
                return self._error("The two passwords don't match.", self.f_confirm)
            self._busy_start("Creating")
            self._bg(lambda: self.app.session.create(pw), self._created)

    def _bg(self, fn: Callable, done: Callable) -> None:
        box: dict = {}

        def work() -> None:
            try:
                box["v"] = fn()
            except BaseException as e:  # noqa: BLE001 — surfaced to the UI below
                box["e"] = e

        t = threading.Thread(target=work, daemon=True)
        self._active_worker = t
        t.start()

        def poll() -> None:
            if not self.winfo_exists():
                return
            if t.is_alive():
                self.after(40, poll)
            else:
                self._active_worker = None
                done(box)

        self.after(40, poll)

    def _busy_start(self, word: str) -> None:
        self._busy = True
        self.err.configure(text="")
        self.submit.set_enabled(False)
        n = [0]

        def tick() -> None:
            if not self._busy or not self.winfo_exists():
                return
            self.submit.configure(text=f"{word}" + "." * (n[0] % 4))
            n[0] += 1
            self._busy_job = self.after(260, tick)

        tick()

    def _busy_end(self) -> None:
        self._busy = False
        if self._busy_job:
            self.after_cancel(self._busy_job)
        if self.winfo_exists():
            self.submit.set_enabled(True)
            self.submit.configure(text="Create Vault" if self.mode == "create" else "Unlock")

    def _unlocked(self, res: dict) -> None:
        self._busy_end()
        if "e" in res:
            e = res["e"]
            if isinstance(e, vault.VaultBusyError):
                self._error(str(e))
            elif isinstance(e, (vault.VaultAuthenticationError, vault.VaultFormatError)):
                message = str(e)
                self._error(message, self.f_pw if isinstance(e, vault.VaultAuthenticationError) else None)
                if isinstance(e, vault.VaultAuthenticationError):
                    self._shake()
                self._busy_start("Checking backup")
                pw = self.f_pw.get()
                self._bg(lambda: vault.backup_is_valid(pw), lambda check: self._recovery_checked(check, pw, message))
            else:
                log.error("unlock failed (%s)", type(e).__name__)
                self._error("Couldn't open the vault. Keep the encrypted file and check the data folder.")
            return
        entries, groups = res["v"]
        self.app.on_unlocked(entries, groups)

    def _recovery_checked(self, check: dict, master_password: str, error_message: str) -> None:
        self._busy_end()
        if check.get("e") is not None or not check.get("v"):
            self._error(error_message)
            return
        ok = confirm(self.winfo_toplevel(), "Restore verified backup?",
                     "The backup authenticates with this password, but the current vault did not open. "
                     "Restoring may return to an older state. The current encrypted file will be preserved beside it "
                     "before any replacement. Continue only if you want to restore this backup.",
                     "Restore backup", danger=True)
        if not ok:
            self._error(error_message)
            return
        self._busy_start("Restoring")
        self._bg(lambda: self.app.session.recover_from_backup(master_password, confirmed=True), self._recovered)

    def _recovered(self, res: dict) -> None:
        self._busy_end()
        if "e" in res:
            self._error("Backup recovery failed; the encrypted files were kept. Close other app instances and try again.")
            return
        entries, groups = res["v"]
        self.app.on_unlocked(entries, groups)

    def _created(self, res: dict) -> None:
        self._busy_end()
        if "e" in res:
            log.error("create failed (%s)", type(res["e"]).__name__)
            self._error("Couldn't create the vault. Check the data folder and available disk space.")
            return
        self.app.on_unlocked([], [])
