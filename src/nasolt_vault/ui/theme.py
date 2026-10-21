"""Windows XP inspired colour tokens, fonts, and window-fitting helpers."""
from __future__ import annotations

import tkinter
import weakref
import sys

import customtkinter as ctk
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

# --------------------------------------------------------------- palette
# XP's blue visual style uses a cream work area, white controls, and dark text.
# The app has one appearance; these are concrete colors rather than dark pairs.
BG            = "#ece9d8"
SIDEBAR       = "#d9e8fb"
SURFACE       = "#ffffff"
SURFACE_2     = "#edf4ff"
INPUT         = "#ffffff"
BORDER        = "#9bb4d0"
BORDER_STRONG = "#7f9db9"
TEXT          = "#111111"
TEXT_MUTED    = "#4b4b4b"
TEXT_FAINT    = "#6a6a6a"
ACCENT        = "#0046d5"
ACCENT_HOVER  = "#1e48a8"
ACCENT_SOFT   = "#cbe0ff"
ACCENT_LINE   = "#f4a126"
ON_ACCENT     = "#ffffff"
SUCCESS       = "#238526"
SUCCESS_SOFT  = "#e0f3d9"
DANGER        = "#b52b22"
DANGER_HOVER  = "#942016"
DANGER_SOFT   = "#ffe7e1"
CLOSE_BG      = "#c32c23"
CLOSE_HOVER   = "#e3483b"
FOLDER        = "#d89b22"
WARNING       = "#a76509"
TITLEBAR      = "#245edb"
TITLEBAR_TEXT = "#ffffff"
TITLEBAR_SUB  = "#deebff"
TITLEBAR_GLOSS = "#72a8fa"
TITLEBAR_SHADOW = "#153a98"
TITLEBAR_BANDS = ("#8cbbff", "#6da5fb", "#4e8cf2", "#3474e8")
BRAND         = "#1c3f93"
BUTTON_FACE   = "#f4f2e8"
BUTTON_HOVER  = "#fff5d9"
BUTTON_GLOSS  = "#ffffff"
BUTTON_SHADOW = "#b6b2a2"
BUTTON_HOT_BORDER = "#e89b2d"
MENU_SELECT   = "#316ac5"

FAMILY = "Tahoma"        # Windows XP UI font; Tk substitutes elsewhere
MONO = "Courier New"

_fonts: dict = {}
_tk_colors: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def reset_tk_cache() -> None:
    """Fonts, like images, belong to the current Tk interpreter."""
    _fonts.clear()
    _tk_colors.clear()


def font(size: int = 13, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    key = (size, weight, mono)
    if key not in _fonts:
        _fonts[key] = ctk.CTkFont(family=MONO if mono else FAMILY, size=size, weight=weight)
    return _fonts[key]


def apply_mode() -> None:
    """The application has one light XP appearance, independent of old preferences."""
    ctk.set_appearance_mode("Light")
    for widget, color in list(_tk_colors.items()):
        try:
            widget.configure(bg=resolve(color))
        except tkinter.TclError:
            pass


def track_tk_color(widget, color) -> None:
    """Color small Tk bevel strips to match the application palette."""
    _tk_colors[widget] = color
    widget.configure(bg=resolve(color))


def style_native_window(win) -> bool:
    """Keep the native Windows 11 controls with a neutral, square caption."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 22000:
        return False
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32")
        dwm = ctypes.WinDLL("dwmapi")
        user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.GetAncestor.restype = ctypes.c_void_p
        dwm.DwmSetWindowAttribute.argtypes = (
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd = user32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()

        def colorref(hex_color: str) -> int:
            return int(hex_color[5:7] + hex_color[3:5] + hex_color[1:3], 16)

        settings = (
            (33, 1),  # DWMWA_WINDOW_CORNER_PREFERENCE: DWMWCP_DONOTROUND
            (34, colorref(resolve(BORDER_STRONG))),
            (35, colorref(resolve(BUTTON_FACE))),
            (36, colorref(resolve(TEXT))),
        )
        results = [dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_uint32(value)), 4)
                   for attr, value in settings]
        return all(result == 0 for result in results)
    except (OSError, AttributeError, tkinter.TclError):
        return False


def resolve(color) -> str:
    """Return a concrete color, accepting legacy CTk color pairs if supplied."""
    if isinstance(color, (tuple, list)):
        return color[0]
    return color


def widget_scale(widget) -> float:
    try:
        return float(ScalingTracker.get_widget_scaling(widget))
    except Exception:
        return 1.0


def window_scale(win) -> float:
    try:
        return float(ScalingTracker.get_window_scaling(win))
    except Exception:
        return 1.0


def fit_window(win, width: int, height: int, min_w: int = 0, min_h: int = 0, taskbar: int = 56) -> tuple[int, int]:
    """
    Size `win` to (width x height) logical pixels but never larger than the usable
    screen, then centre it. CustomTkinter scales the size but NOT the position, so the
    position is computed here in physical pixels. Returns the logical size applied.
    """
    win.update_idletasks()
    s = window_scale(win)
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()          # physical
    max_w = int(sw / s) - 16
    max_h = int((sh - taskbar * s) / s) - 40                              # minus title bar
    w = max(min(width, max_w), min(min_w, max_w))
    h = max(min(height, max_h), min(min_h, max_h))
    x = max(0, int((sw - w * s) / 2))
    y = max(0, int((sh - taskbar * s - (h + 32) * s) / 2))
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.minsize(min(min_w, w), min(min_h, h))
    return w, h
