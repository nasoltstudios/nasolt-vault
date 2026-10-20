"""Session-bound authentication routing for Vault Summon."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

import app_settings
import clipboard
import hello_enrollment
import vault
import windows_hello
from windows_startup import sync_cold_start_links
from windows_shortcuts import SUMMON_OPTIONS, WindowsHotkeys, active_desktop_available


def find_accounts(entries, query: str) -> list[dict[str, str]]:
    """Return display-only records; passwords and notes never enter search UI."""
    terms = query.casefold().split()
    found = []
    for entry in entries:
        title = str(entry.get("title") or "Untitled")
        username = str(entry.get("username") or "")
        url = str(entry.get("url") or "")
        if all(term in " ".join((title, username, url)).casefold() for term in terms):
            found.append({"id": entry["id"], "title": title,
                          "username": username, "url": url})
    return sorted(found, key=lambda item: item["title"].casefold())


@dataclass
class AccessRequest:
    ident: int
    epoch: int
    route: str
    destination: str
    await_login: bool = False
    state: str = "pending"
    origin_state: str = "normal"


class QuickAccess:
    POLL_MS = 50

    def __init__(self, app, hotkeys=None):
        self.app = app
        self.hotkeys = hotkeys if hotkeys is not None else WindowsHotkeys()
        self.summon_popup = None
        self.reauth_prompt = None
        self.request: AccessRequest | None = None
        self.last_state = "idle"
        self._grant_id: int | None = None
        self._counter = 0
        self._epoch = 0
        self._event_floor = time.monotonic()
        self._auth_results: queue.Queue[tuple[int, int, str, object]] = queue.Queue()
        self._auth_worker: threading.Thread | None = None
        self._hello_cancel: threading.Event | None = None
        self._stopped = False
        self._job = None
        self._timeout = 30
        self.configure_from_settings()
        self._poll()

    def configure_from_settings(self):
        settings = app_settings.load_settings()
        summon = settings.get("summon_shortcut", "ctrl+alt+n")
        self._summon_key = summon if summon in SUMMON_OPTIONS else "off"
        timeout = settings.get("summon_timeout_seconds", 30)
        self._timeout = timeout if type(timeout) is int and timeout in (15, 30, 60, 120) else 30
        self.revoke()
        if settings.get("cold_start_shortcuts", False) and self._summon_key == "ctrl+alt+n":
            result = sync_cold_start_links(True)
            if result == "enabled":
                self.hotkeys.configure("off")
                self.hotkeys.status = {"summon": "Shell shortcut"}
                return self.status()
        else:
            sync_cold_start_links(False)
        return self.hotkeys.configure(self._summon_key)

    def status(self):
        return dict(self.hotkeys.status)

    def _session_valid(self):
        shell = self.app.shell
        return (not self._stopped and self.app.session.is_open and shell is not None
                and shell.session is self.app.session and bool(shell.winfo_exists()))

    def _authorized(self, epoch=None):
        request = self.request
        return (self._session_valid() and request is not None and request.state == "authorized"
                and self._grant_id == request.ident and request.epoch == self._epoch
                and (epoch is None or epoch == self._epoch)
                and self.app.session.matches_disk())

    def search(self, query, epoch=None):
        return find_accounts(self.app.shell.entries, query) if self._authorized(epoch) else []

    def copy_field(self, entry_id, field, epoch=None):
        if field not in ("username", "password") or not self._authorized(epoch):
            return False
        entry = vault.get_entry_by_id(self.app.shell.entries, entry_id)
        if entry is None:
            return False
        value = entry.get(field) or ""
        if not value:
            self.app.shell.notify("Nothing to copy", f"This entry has no {field}.", "info")
            return False
        if not clipboard.copy_to_clipboard(value):
            self.app.shell.notify("Couldn't copy", "The clipboard is unavailable.", "error")
            return False
        self.app.shell.notify(f"Copied {field}", f"Clears in {clipboard.COPY_TIMEOUT_SECONDS}s.", "copy")
        return True

    def request_normal(self, destination="summon"):
        """Every invocation creates a fresh authentication request, even if unlocked."""
        if self._stopped:
            return None
        if self.request is not None and self.request.state == "pending" and self.request.route == "normal":
            self._bring_auth_forward()
            return self.request.ident
        if not vault.vault_exists():
            self.app.open_window()
            return None
        self.revoke()
        self._counter += 1
        request = AccessRequest(self._counter, self._epoch, "normal", destination,
                                await_login=not self._session_valid(),
                                origin_state=self.app.state())
        self.request = request
        self.last_state = "pending_normal"
        from ui.reauth_prompt import ReauthPrompt
        enrolled = (not request.await_login and destination == "summon" and
                    hello_enrollment.read(self.app.session))
        self.reauth_prompt = ReauthPrompt(
            self.app,
            lambda password, rid=request.ident: self._verify_async(rid, password),
            lambda rid=request.ident: self.cancel_request(rid),
            "Settings" if destination == "settings" else "Vault Summon",
            locked=request.await_login,
            on_open_full=lambda rid=request.ident: self._open_full_vault(rid),
            on_hello=(lambda rid=request.ident: self._verify_hello_async(rid)) if enrolled else None)
        if enrolled and enrolled["prefer"]:
            self.app.after(10, lambda rid=request.ident: self._verify_hello_async(rid))
        return request.ident

    def _bring_auth_forward(self):
        if self.reauth_prompt is not None:
            self.reauth_prompt.bring_forward()
        else:
            self._show_login()

    def _open_full_vault(self, ident):
        if self.request is None or self.request.ident != ident:
            return
        self.cancel_request(ident)
        self.app.open_window()

    def _verify_async(self, ident, password):
        request = self.request
        if request is None or request.ident != ident or request.state != "pending":
            return
        if self._auth_worker is not None and self._auth_worker.is_alive():
            if self.reauth_prompt is not None:
                self.reauth_prompt.show_error("Authentication is already in progress.")
            return
        epoch = self._epoch
        locked = request.await_login

        def work():
            try:
                if locked:
                    result = self.app.session.open(password)
                    outcome = "opened"
                else:
                    result = self.app.session.verify_master_password(password)
                    outcome = "verified" if result else "rejected"
            except vault.VaultAuthenticationError:
                outcome, result = "rejected", None
            except vault.VaultBusyError:
                outcome, result = "busy", None
            except vault.VaultFormatError:
                outcome, result = "damaged", None
            except Exception as exc:
                logging.getLogger("nasolt.quick_access").error("reauth failed (%s)", type(exc).__name__)
                outcome, result = "error", None
            self._auth_results.put((ident, epoch, outcome, result))

        self._auth_worker = threading.Thread(target=work, daemon=True, name="NasoltReauth")
        self._auth_worker.start()

    def _verify_hello_async(self, ident):
        request = self.request
        if (request is None or request.ident != ident or request.state != "pending"
                or request.await_login or not self._session_valid()
                or hello_enrollment.read(self.app.session) is None):
            return
        if self._auth_worker is not None and self._auth_worker.is_alive():
            return
        if self.reauth_prompt is None:
            return
        from windows_focus import window_handle
        hwnd = window_handle(self.reauth_prompt)
        if not hwnd:
            self.reauth_prompt.show_error("Windows Hello is unavailable. Use your master password.")
            return
        cancel = threading.Event()
        self._hello_cancel = cancel
        self.reauth_prompt.show_status("Waiting for Windows Hello…")
        epoch = self._epoch

        def work():
            result = windows_hello.verify(hwnd, cancel=cancel)
            self._auth_results.put((ident, epoch, "hello", result))

        self._auth_worker = threading.Thread(target=work, daemon=True, name="NasoltHello")
        self._auth_worker.start()

    def _process_auth_results(self):
        while True:
            try:
                ident, epoch, outcome, result = self._auth_results.get_nowait()
            except queue.Empty:
                return
            request = self.request
            if (request is None or request.ident != ident or request.epoch != epoch
                    or epoch != self._epoch or request.state != "pending"):
                if outcome == "opened" and self.app.shell is None:
                    self.app.session.close()
                continue
            if outcome == "opened" and request.await_login:
                if self.reauth_prompt is not None:
                    self.reauth_prompt.close()
                    self.reauth_prompt = None
                self.app.on_unlocked(*result, reveal=request.origin_state == "normal")
            elif outcome == "hello" and not request.await_login:
                if (result == "verified" and self._session_valid() and
                        self.app.session.matches_disk() and
                        hello_enrollment.read(self.app.session) is not None):
                    if self.reauth_prompt is not None:
                        self.reauth_prompt.close()
                        self.reauth_prompt = None
                    self._grant(request)
                elif self.reauth_prompt is not None:
                    message = ("Windows Hello was canceled. Use your master password." if result == "canceled" else
                               "Windows Hello did not verify. Use your master password.")
                    self.reauth_prompt.show_error(message)
            elif outcome == "verified" and not request.await_login and self._session_valid():
                if self.reauth_prompt is not None:
                    self.reauth_prompt.close()
                    self.reauth_prompt = None
                self._grant(request)
            elif outcome == "damaged" and request.await_login:
                self.authentication_failed(ident)
                self.app.open_window()
                if self.app.login is not None:
                    self.app.login._error("Vault could not open. Use the full window to check backup recovery.")
            elif outcome in ("rejected", "busy") and request.await_login:
                if self.reauth_prompt is not None:
                    self.reauth_prompt.show_error("Password not accepted." if outcome == "rejected" else
                                                  "Vault is in use. Close other copies and retry.")
            else:
                self.authentication_failed(ident)
                self.app.toasts.show("Authentication failed", "Quick access was not opened.", "error")

    def on_session_unlocked(self):
        request = self.request
        if (request is not None and request.state == "pending" and request.route == "normal"
                and request.await_login and request.epoch == self._epoch and self._session_valid()):
            self._grant(request)
        else:
            self.revoke()

    def _grant(self, request):
        if (request is not self.request or request.epoch != self._epoch
                or not self._session_valid() or not self.app.session.matches_disk()):
            return False
        request.state = "authorized"
        self._grant_id = request.ident
        self.last_state = "authorized"
        if request.destination == "summon":
            return self.open_summon(request.ident)
        if request.destination == "settings":
            self.app.open_settings()
        return True

    def open_summon(self, request_id=None):
        if not self._authorized() or (request_id is not None and request_id != self._grant_id):
            return False
        if self.summon_popup is not None:
            self.summon_popup.lift()
            self.summon_popup.focus_force()
            self.summon_popup.query.focus_set()
            return True
        from ui.summon_popup import SummonPopup
        epoch = self._epoch
        self.app._touch()
        self.summon_popup = SummonPopup(
            self.app, lambda q: self.search(q, epoch),
            lambda entry_id, field: self.copy_field(entry_id, field, epoch),
            lambda: setattr(self, "summon_popup", None), self.app._touch, self._timeout)
        return True

    def authentication_failed(self, ident=None):
        if self.request is None or (ident is not None and self.request.ident != ident):
            return
        self.last_state = "failed"
        self._drop_request()

    def cancel_request(self, ident=None):
        if self.request is None or (ident is not None and self.request.ident != ident):
            return
        self.last_state = "cancelled"
        self._drop_request()

    def _drop_request(self):
        if self._hello_cancel is not None:
            self._hello_cancel.set()
            self._hello_cancel = None
        self._epoch += 1
        self._event_floor = time.monotonic()
        self.request = None
        self._grant_id = None
        if self.app.login is not None:
            self.app.login.hide_quick_request()
        if self.reauth_prompt is not None:
            popup, self.reauth_prompt = self.reauth_prompt, None
            popup.close()
        if self.summon_popup is not None:
            popup, self.summon_popup = self.summon_popup, None
            popup.close()

    def revoke(self):
        self.last_state = "revoked"
        self.hotkeys.drain()
        self._drop_request()

    def _show_login(self):
        self.app.deiconify()
        self.app.lift()
        if self.app.login is not None:
            self.app.login.f_pw.focus()

    def _poll(self):
        if self._stopped:
            return
        try:
            if self.app.shell is not None and not self.app.session.is_open:
                self.app.show_login("Vault session ended. Unlock to continue.",
                                    preserve_hidden=self.app.state() == "withdrawn")
            if self.app.session.is_open and not active_desktop_available():
                self.app.show_login("Vault locked when the Windows desktop changed.",
                                    preserve_hidden=self.app.state() == "withdrawn")
            elif (self.request is not None and self.request.state == "authorized"
                  and not self.app.session.matches_disk()):
                self.revoke()
            elif ((self.summon_popup is not None or self.reauth_prompt is not None)
                  and not active_desktop_available()):
                self.revoke()
            self._process_auth_results()
            for issued, kind in self._drain_events():
                if issued < self._event_floor or not active_desktop_available():
                    continue
                if kind == "summon":
                    self.request_normal()
            instance = getattr(self.app, "instance", None)
            if instance is not None:
                for route in instance.drain_requests():
                    if route == "normal":
                        self.request_normal()
                    elif route == "open":
                        self.app.open_window()
            tray = getattr(self.app, "tray", None)
            if tray is not None:
                for action in tray.drain():
                    self.app.tray_action(action)
        except Exception as exc:
            logging.getLogger("nasolt.quick_access").error("quick access poll failed (%s)", type(exc).__name__)
            self.revoke()
        finally:
            if not self._stopped:
                self._job = self.app.after(self.POLL_MS, self._poll)

    def _drain_events(self):
        events = []
        while True:
            try:
                events.append(self.hotkeys.events.get_nowait())
            except queue.Empty:
                return events

    def stop(self):
        self._stopped = True
        if self._hello_cancel is not None:
            self._hello_cancel.set()
        if self._job is not None:
            self.app.after_cancel(self._job)
            self._job = None
        self.revoke()
        self.hotkeys.stop()

    def cancel_native_authentication(self):
        if self._hello_cancel is not None:
            self._hello_cancel.set()
