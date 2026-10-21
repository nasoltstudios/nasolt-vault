"""Windows hotkeys. The worker only queues events; Tk stays on its own thread."""
from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
DESKTOP_READOBJECTS = 0x0001

# Global Shift+letter combinations can suppress normal typing. The default
# Ctrl+Alt+N is configured in app_settings; users can turn it off.
SHORTCUTS = {
    "off": None,
    "shift+n": (MOD_SHIFT, ord("N")),
    "ctrl+alt+n": (MOD_CONTROL | MOD_ALT, ord("N")),
    "ctrl+shift+n": (MOD_CONTROL | MOD_SHIFT, ord("N")),
}
SUMMON_OPTIONS = ("off", "shift+n", "ctrl+alt+n", "ctrl+shift+n")


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Message(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", _Point), ("lPrivate", wintypes.DWORD)]


class _Rect(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", wintypes.DWORD)]


def _user32():
    return ctypes.WinDLL("user32", use_last_error=True)


def active_desktop_available() -> bool:
    """Fail closed when the input desktop is not the normal user desktop."""
    if sys.platform != "win32":
        return False
    user32 = _user32()
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD))
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
    user32.CloseDesktop.restype = wintypes.BOOL
    desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desktop:
        return False
    try:
        name = ctypes.create_unicode_buffer(128)
        needed = wintypes.DWORD()
        ok = user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed))
        return bool(ok and name.value.casefold() == "default")
    finally:
        user32.CloseDesktop(desktop)


def chord_is_held(shortcut: str) -> bool:
    """Read key state without installing a keyboard hook or swallowing keys."""
    spec = SHORTCUTS.get(shortcut)
    if sys.platform != "win32" or spec is None or not active_desktop_available():
        return False
    modifiers, key = spec
    user32 = _user32()
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    keys = [key]
    if modifiers & MOD_SHIFT:
        keys.append(0x10)
    if modifiers & MOD_CONTROL:
        keys.append(0x11)
    if modifiers & MOD_ALT:
        keys.append(0x12)
    return all(user32.GetAsyncKeyState(k) & 0x8000 for k in keys)


def active_monitor_work_area(fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Physical-pixel work area of the monitor containing the foreground window."""
    if sys.platform != "win32":
        return fallback
    try:
        user32 = _user32()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MonitorInfo))
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom
    except (OSError, AttributeError):
        pass
    return fallback


class WindowsHotkeys:
    """RegisterHotKey runs on a dedicated message thread; events carry no secrets."""

    def __init__(self) -> None:
        self.events: queue.Queue[tuple[float, str]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.status: dict[str, str] = {"summon": "off"}

    def configure(self, summon: str) -> dict[str, str]:
        self.stop()
        if self._thread is not None:
            self.status = {"summon": "unavailable"}
            return dict(self.status)
        self.status = {"summon": "off"}
        if sys.platform != "win32":
            if summon != "off":
                self.status["summon"] = "Windows only"
            return dict(self.status)
        requested = {"summon": summon}
        if summon == "off":
            return dict(self.status)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, args=(requested,), daemon=True, name="NasoltHotkeys")
        self._thread.start()
        if not self._ready.wait(2.0):
            self.status = {kind: "unavailable" if value != "off" else "off"
                           for kind, value in requested.items()}
        return dict(self.status)

    def _run(self, requested: dict[str, str]) -> None:
        try:
            self._message_loop(requested)
        except Exception:
            self.status = {kind: "unavailable" if value != "off" else "off"
                           for kind, value in requested.items()}
            self._ready.set()

    def _message_loop(self, requested: dict[str, str]) -> None:
        user32 = _user32()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.PeekMessageW.argtypes = (ctypes.POINTER(_Message), wintypes.HWND,
                                        wintypes.UINT, wintypes.UINT, wintypes.UINT)
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = (ctypes.POINTER(_Message), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user32.GetMessageW.restype = ctypes.c_int
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        message = _Message()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
        self._thread_id = kernel32.GetCurrentThreadId()
        registered: dict[int, str] = {}
        try:
            for hotkey_id, (kind, shortcut) in enumerate(requested.items(), start=0x4E00):
                if shortcut == "off":
                    continue
                spec = SHORTCUTS.get(shortcut)
                if spec is None:
                    self.status[kind] = "invalid shortcut"
                    continue
                modifiers, key = spec
                if user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, key):
                    registered[hotkey_id] = kind
                    self.status[kind] = "active"
                else:
                    error = ctypes.get_last_error()
                    self.status[kind] = ("unavailable (shortcut in use)" if error == 1409 else
                                         "unavailable (Windows denied registration)" if error == 5 else
                                         f"unavailable (Windows error {error})")
            self._ready.set()
            if registered:
                while True:
                    result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                    if result <= 0:
                        break
                    if message.message == WM_HOTKEY and message.wParam in registered:
                        self.events.put((time.monotonic(), registered[message.wParam]))
        finally:
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)
            self._thread_id = 0
            self._ready.set()

    def drain(self) -> None:
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return

    def stop(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive() and self._thread_id:
            user32 = _user32()
            user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT,
                                                   wintypes.WPARAM, wintypes.LPARAM)
            user32.PostThreadMessageW.restype = wintypes.BOOL
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            thread.join(timeout=2.0)
        if thread is not None and thread.is_alive():
            return
        self._thread = None
        self._thread_id = 0
        self.drain()
