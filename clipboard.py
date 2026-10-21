"""
clipboard.py — clipboard copy with automatic clear.

Bug fixed vs. the earlier version: the old timer blindly wiped the clipboard
30 seconds after the last copy, even if the user had since copied something
unrelated (their own text vanished). We now remember what WE put on the
clipboard and only clear it if it is still that exact value.
"""
from __future__ import annotations

import threading
from typing import Optional

import pyperclip

COPY_TIMEOUT_SECONDS: int = 30

_lock = threading.RLock()
_timer: Optional[threading.Timer] = None
_last_secret: Optional[str] = None
_generation = 0


def _clear_if_ours(generation: Optional[int] = None) -> None:
    global _last_secret, _timer
    with _lock:
        if generation is not None and generation != _generation:
            return  # A canceled timer may already have entered its callback.
        secret = _last_secret
        _last_secret = None
        _timer = None
        if secret is None:
            return
        try:
            if pyperclip.paste() == secret:
                pyperclip.copy("")
        except Exception:
            pass  # clipboard busy / unavailable — best effort


def _stop_timer() -> None:
    global _timer
    if _timer is not None:
        _timer.cancel()
        _timer = None


def copy_to_clipboard(text: str, timeout: int = COPY_TIMEOUT_SECONDS) -> bool:
    """Copy *text* and schedule an auto-clear (only if the clipboard still holds it)."""
    global _timer, _last_secret, _generation
    if not text:
        return False
    with _lock:
        try:
            pyperclip.copy(text)
        except Exception:
            return False
        _stop_timer()
        _generation += 1
        _last_secret = text
        _timer = threading.Timer(timeout, _clear_if_ours, args=(_generation,))
        _timer.daemon = True
        _timer.start()
    return True


def copy_without_clear(text: str) -> bool:
    """Copy to clipboard WITHOUT scheduling an auto-clear."""
    global _last_secret, _generation
    with _lock:
        try:
            pyperclip.copy(text)
        except Exception:
            return False
        _stop_timer()
        _generation += 1
        _last_secret = None
    return True


def clear_now() -> None:
    """Clear right away (used when the vault locks / the app closes)."""
    with _lock:
        _stop_timer()
        _clear_if_ours()


manual_clear = clear_now
