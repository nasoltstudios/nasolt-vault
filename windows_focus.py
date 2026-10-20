"""One-shot Win32 activation for shortcut popups; never overrides foreground policy."""
from __future__ import annotations

import ctypes
import sys
import tkinter
from ctypes import wintypes

GA_ROOT = 2
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
FLASHW_TRAY = 0x00000002


class _FlashInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD)]


def window_handle(window) -> int:
    if sys.platform != "win32":
        return 0
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    return int(user32.GetAncestor(window.winfo_id(), GA_ROOT) or window.winfo_id())


def activate_window(window, focus_widget=None) -> bool:
    """Show and request foreground once; focus the field only if Windows grants it."""
    try:
        window.deiconify()
        window.lift()
        window.update_idletasks()
        if sys.platform != "win32":
            target = focus_widget or window
            (target.focus if hasattr(target, "focus") else target.focus_set)()
            return bool(window.winfo_viewable())
        hwnd = window_handle(window)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsIconic.argtypes = (wintypes.HWND,)
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.restype = wintypes.HWND
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(hwnd)
        foreground = user32.GetForegroundWindow() == hwnd
        if foreground:
            target = focus_widget or window
            (target.focus if hasattr(target, "focus") else target.focus_set)()
        else:
            # Windows may deny foreground activation. Notify without stealing it.
            user32.FlashWindowEx.argtypes = (ctypes.POINTER(_FlashInfo),)
            user32.FlashWindowEx.restype = wintypes.BOOL
            info = _FlashInfo(ctypes.sizeof(_FlashInfo), hwnd, FLASHW_TRAY, 2, 0)
            user32.FlashWindowEx(ctypes.byref(info))
        return foreground and bool(window.winfo_viewable())
    except (OSError, tkinter.TclError, AttributeError):
        return False
