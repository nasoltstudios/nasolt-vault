"""Native per-process Windows notification icon; no extra Tk root or dependency."""
from __future__ import annotations

import ctypes
import itertools
import os
import queue
import sys
import threading
from ctypes import wintypes

from .paths import resource_path
from .windows_shortcuts import _Message

WM_APP = 0x8000
WM_TRAY = WM_APP + 23
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
NIN_SELECT, NIN_KEYSELECT = 0x0400, 0x0401
NIM_ADD, NIM_DELETE, NIM_SETVERSION = 0, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
TPM_RIGHTBUTTON, TPM_RETURNCMD = 2, 0x100
MF_STRING, MF_SEPARATOR = 0, 0x800

WNDPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM) if sys.platform == "win32" else None
_SHELL32 = ctypes.WinDLL("shell32", use_last_error=True) if sys.platform == "win32" else None
_USER32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None


class _WndClass(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC or ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON)]


class _NotifyIcon(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


class TrayIcon:
    ACTIONS = {1: "open", 2: "lock", 3: "settings", 4: "exit"}
    _serials = itertools.count()

    def __init__(self):
        serial = next(self._serials)
        self._class_name = f"NasoltVaultTray_{os.getpid()}" + (f"_{serial}" if serial else "")
        self.events: queue.Queue[str] = queue.Queue()
        self._thread = None
        self._ready = threading.Event()
        self._hwnd = None
        self._wndproc = None
        self.active = False
        self.last_error = ""
        self.phase = "idle"
        self._stop_requested = False

    def start(self) -> bool:
        if not self.start_async():
            return False
        self._ready.wait(10)
        return self.active

    def start_async(self) -> bool:
        if self.active:
            return True
        if sys.platform != "win32":
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._ready.clear()
        self.last_error = ""
        self.phase = "starting"
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="NasoltTray")
        self._thread.start()
        return True

    def _run(self):
        user32, shell32, kernel32 = _USER32, _SHELL32, _KERNEL32
        self.phase = "binding Win32 APIs"
        user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.restype = wintypes.LPARAM
        user32.RegisterClassExW.argtypes = (ctypes.POINTER(_WndClass),)
        user32.RegisterClassExW.restype = wintypes.WORD
        user32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                           wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.GetMessageW.argtypes = (ctypes.POINTER(_Message), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user32.GetMessageW.restype = ctypes.c_int
        shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.POINTER(_NotifyIcon))
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        class_name = self._class_name
        instance = kernel32.GetModuleHandleW(None)
        self.phase = "creating Win32 callback"

        def proc(hwnd, message, wparam, lparam):
            if message == WM_TRAY:
                event = lparam & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT, NIN_KEYSELECT):
                    self.events.put("open")
                elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu(user32, hwnd)
                return 0
            if message == WM_COMMAND:
                action = self.ACTIONS.get(wparam & 0xFFFF)
                if action:
                    self.events.put(action)
                return 0
            if message == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._wndproc = WNDPROC(proc)
        self.phase = "preparing tray class"
        cls = _WndClass()
        cls.cbSize = ctypes.sizeof(cls)
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = instance
        cls.lpszClassName = class_name
        icon = None
        hwnd = None
        nid = None
        registered = False
        try:
            self.phase = "registering window class"
            if not user32.RegisterClassExW(ctypes.byref(cls)):
                self.last_error = f"RegisterClassExW: {ctypes.get_last_error()}"
                return
            registered = True
            self.phase = "creating tray window"
            hwnd = user32.CreateWindowExW(0, class_name, "Nasolt Vault tray", 0,
                                          0, 0, 0, 0, None, None, instance, None)
            if not hwnd:
                self.last_error = f"CreateWindowExW: {ctypes.get_last_error()}"
                return
            self._hwnd = hwnd
            if self._stop_requested:
                return
            self.phase = "loading icon"
            user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT)
            user32.LoadImageW.restype = wintypes.HANDLE
            icon = user32.LoadImageW(None, resource_path("assets", "app.ico"), 1, 16, 16, 0x10)
            if not icon:
                self.last_error = f"LoadImageW: {ctypes.get_last_error()}"
                return
            if self._stop_requested:
                return
            nid = _NotifyIcon()
            nid.cbSize = ctypes.sizeof(nid)
            nid.hWnd = hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = icon
            nid.szTip = "Nasolt Vault"
            self.phase = "adding tray icon"
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                self.last_error = f"Shell_NotifyIconW: {ctypes.get_last_error()}"
                return
            self.active = True
            self.phase = "active"
            if self._stop_requested:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            nid.uVersion = 4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
            self._ready.set()
            msg = _Message()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self.active = False
            if nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            if hwnd:
                user32.DestroyWindow(hwnd) if user32.IsWindow(hwnd) else None
            if icon:
                user32.DestroyIcon(icon)
            self._hwnd = None
            if registered:
                user32.UnregisterClassW(class_name, instance)
            self._ready.set()

    def _show_menu(self, user32, hwnd):
        user32.CreatePopupMenu.restype = wintypes.HMENU
        menu = user32.CreatePopupMenu()
        try:
            for ident, label in ((1, "Open Vault"), (2, "Lock Vault"),
                                 (3, "Settings"), (0, ""), (4, "Exit")):
                user32.AppendMenuW(menu, MF_SEPARATOR if ident == 0 else MF_STRING, ident, label)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)
            user32.TrackPopupMenu.restype = wintypes.UINT
            selected = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                              point.x, point.y, 0, hwnd, None)
            if selected in self.ACTIONS:
                self.events.put(self.ACTIONS[selected])
        finally:
            user32.DestroyMenu(menu)

    def drain(self):
        actions = []
        while True:
            try:
                actions.append(self.events.get_nowait())
            except queue.Empty:
                return actions

    def stop(self):
        self._stop_requested = True
        if self._hwnd:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                return
        self._thread = None
