"""
widgets.py — the small component kit every screen is built from.

Everything uses the light XP palette and is animated with ui.anim:
  Btn, IconBtn, Tooltip, Field, Popup / Dropdown / Menu, StrengthMeter, Toasts,
  plus tiny factories: card(), divider(), check(), slider().
"""
from __future__ import annotations

import tkinter
from typing import Callable, List, Optional, Sequence, Tuple

import customtkinter as ctk

from .. import icons
from . import theme as T
from .anim import animate, cancel_owned_after_jobs, tween_color

Option = Tuple[str, str]  # (key, label)


# ---------------------------------------------------------------- utilities
def hand(widget) -> None:
    """Pointer cursor on a widget and its inner tk parts."""
    for w in (widget, getattr(widget, "_canvas", None), getattr(widget, "_label", None),
              getattr(widget, "_text_label", None)):
        if w is not None:
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass


def keyboard_button(button, normal_border: int) -> None:
    """Give CustomTkinter's canvas-backed buttons a visible keyboard action."""
    button._canvas.configure(takefocus=1)
    button.bind("<Return>", lambda e: (button.invoke(), "break")[1], add="+")
    button.bind("<space>", lambda e: (button.invoke(), "break")[1], add="+")

    def focus_in(_event):
        button._normal_focus_border = (button.cget("border_width"), button.cget("border_color"))
        button.configure(border_width=2, border_color=T.ACCENT)

    def focus_out(_event):
        width, color = getattr(button, "_normal_focus_border", (normal_border, T.BORDER))
        button.configure(border_width=width, border_color=color)

    button._canvas.bind("<FocusIn>", focus_in, add="+")
    button._canvas.bind("<FocusOut>", focus_out, add="+")


def fit_text(text: str, fnt: ctk.CTkFont, max_px: float, ellipsis_left: bool = False) -> str:
    """Trim `text` with an ellipsis so it fits max_px (logical pixels)."""
    text = " ".join((text or "").split())          # tabs / newlines / runs of spaces -> single spaces
    if max_px <= 8 or fnt.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        cand = ("…" + text[-mid:]) if ellipsis_left else (text[:mid] + "…")
        if fnt.measure(cand) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return "…"
    return ("…" + text[-lo:]) if ellipsis_left else (text[:lo] + "…")


def card(parent, **kw) -> ctk.CTkFrame:
    opts = dict(fg_color=T.SURFACE, border_width=1, border_color=T.BORDER_STRONG, corner_radius=2)
    opts.update(kw)
    return ctk.CTkFrame(parent, **opts)


def groupbox(parent, title: str, background=T.BG) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
    """An XP property-page group: a caption interrupts its one-pixel outline."""
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    outline = ctk.CTkFrame(frame, fg_color=background, border_width=1,
                           border_color=T.BORDER_STRONG, corner_radius=0)
    outline.pack(fill="both", expand=True, pady=(9, 0))
    content = ctk.CTkFrame(outline, fg_color="transparent", corner_radius=0)
    content.pack(fill="both", expand=True, padx=14, pady=(17, 13))
    caption = ctk.CTkLabel(frame, text=f" {title} ", fg_color=background,
                           text_color=T.ACCENT, font=T.font(12, "bold"), height=19)
    caption.place(x=10, y=0)
    caption.lift()
    return frame, content


def titlebar(parent, height: int = 76) -> ctk.CTkFrame:
    """Luna blue page chrome with a narrow glossy band and dark lower edge."""
    frame = ctk.CTkFrame(parent, fg_color=T.TITLEBAR, corner_radius=0, height=height)
    frame.pack_propagate(False)
    frame.grid_propagate(False)
    bands = []
    scale = T.widget_scale(frame)
    unit = max(2, round(2 * scale))
    for i, color in enumerate(T.TITLEBAR_BANDS):
        band = tkinter.Frame(frame, bd=0, highlightthickness=0)
        T.track_tk_color(band, color)
        band.place(relx=0, y=i * unit, relwidth=1, height=unit)
        bands.append(band)
    gloss = tkinter.Frame(frame, bd=0, highlightthickness=0)
    T.track_tk_color(gloss, T.TITLEBAR_GLOSS)
    gloss.place(relx=0, rely=1, y=-3, anchor="sw", relwidth=1, height=1)
    shadow = tkinter.Frame(frame, bd=0, highlightthickness=0)
    T.track_tk_color(shadow, T.TITLEBAR_SHADOW)
    shadow.place(relx=0, rely=1, anchor="sw", relwidth=1, height=2)
    frame.after_idle(lambda: [band.tkraise() for band in (*bands, gloss, shadow) if band.winfo_exists()])
    return frame


def divider(parent, vertical: bool = False, color=T.BORDER) -> tkinter.Frame:
    """A one-pixel rule that remains visible at Windows display scaling."""
    rule = tkinter.Frame(parent, bd=0, highlightthickness=0)
    T.track_tk_color(rule, color)
    pixels = max(1, round(T.widget_scale(parent)))
    rule.configure(width=pixels if vertical else 1, height=1 if vertical else pixels)
    return rule


def style_scrollbar(scrollable: ctk.CTkScrollableFrame) -> None:
    """Square Luna-style thumb that appears only when scrolling is possible."""
    bar = scrollable._scrollbar
    bar.configure(
        width=14, corner_radius=0, border_spacing=1,
        fg_color=T.BUTTON_FACE, button_color=T.BORDER_STRONG,
        button_hover_color=T.ACCENT)
    canvas = scrollable._parent_canvas
    visible = [True]

    def sync(first, last):
        try:
            bar.set(first, last)
            needed = float(first) > 0.001 or float(last) < 0.999
            if needed != visible[0]:
                visible[0] = needed
                if needed:
                    bar.grid()
                else:
                    bar.grid_remove()
        except tkinter.TclError:
            pass

    scrollable._xp_scroll_sync = sync
    canvas.configure(yscrollcommand=sync)
    scrollable.after_idle(lambda: sync(*canvas.yview()) if scrollable.winfo_exists() else None)


def inset_edges(widget, color=T.BORDER_STRONG) -> tuple[tkinter.Frame, tkinter.Frame]:
    """One-pixel inner shadow on the top and left of a classic input control."""
    top = tkinter.Frame(widget, bd=0, highlightthickness=0)
    left = tkinter.Frame(widget, bd=0, highlightthickness=0)
    for edge in (top, left):
        T.track_tk_color(edge, color)
    top.place(x=1, y=1, relwidth=1, width=-2, height=1)
    left.place(x=1, y=1, relheight=1, height=-2, width=1)
    return top, left


def check(parent, text: str, variable, command=None) -> ctk.CTkCheckBox:
    return ctk.CTkCheckBox(
        parent, text=text, variable=variable, command=command, font=T.font(12), text_color=T.TEXT,
        fg_color=T.SURFACE, hover_color=T.BUTTON_HOVER, border_color=T.BORDER_STRONG,
        checkmark_color=T.SUCCESS, corner_radius=0, border_width=1, checkbox_width=16, checkbox_height=16)


class XPSlider(ctk.CTkFrame):
    """Pointed-thumb XP slider; mouse and keyboard change the same integer value."""

    def __init__(self, master, from_: int, to: int, command=None, width: int = 260):
        if to <= from_:
            raise ValueError("Slider maximum must exceed its minimum")
        super().__init__(master, width=width, height=25, fg_color="transparent", corner_radius=0)
        self._from, self._to, self._command = from_, to, command
        self._value = from_
        self._hot = self._focused = False
        self._slider_canvas = tkinter.Canvas(self, height=25, bg=parent_bg(self), bd=0,
                                      highlightthickness=0, takefocus=1, cursor="hand2")
        self._slider_canvas.pack(fill="both", expand=True)
        self._slider_canvas.bind("<Configure>", self._draw_slider, add="+")
        self._slider_canvas.bind("<Button-1>", self._click, add="+")
        self._slider_canvas.bind("<B1-Motion>", self._click, add="+")
        self._slider_canvas.bind("<Enter>", lambda e: self._hover(True), add="+")
        self._slider_canvas.bind("<Leave>", lambda e: self._hover(False), add="+")
        self._slider_canvas.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self._slider_canvas.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        for key, value in (("Left", -1), ("Down", -1), ("Right", 1), ("Up", 1),
                           ("Prior", -10), ("Next", 10)):
            self._slider_canvas.bind(f"<{key}>", lambda e, delta=value: self._change(self._value + delta), add="+")
        self._slider_canvas.bind("<Home>", lambda e: self._change(self._from), add="+")
        self._slider_canvas.bind("<End>", lambda e: self._change(self._to), add="+")

    def get(self) -> int:
        return self._value

    def set(self, value: int) -> None:
        self._value = max(self._from, min(self._to, int(round(value))))
        self._draw_slider()

    def _change(self, value: int) -> str:
        old = self._value
        self.set(value)
        if self._value != old and self._command:
            self._command(float(self._value))
        return "break"

    def _click(self, event) -> None:
        self._slider_canvas.focus_set()
        width = max(1, self._slider_canvas.winfo_width() - 20)
        ratio = max(0.0, min(1.0, (event.x - 10) / width))
        self._change(self._from + round(ratio * (self._to - self._from)))

    def _hover(self, on: bool) -> None:
        self._hot = on
        self._draw_slider()

    def _focus(self, on: bool) -> None:
        self._focused = on
        self._draw_slider()

    def _draw_slider(self, _event=None) -> None:
        canvas = self._slider_canvas
        if not canvas.winfo_exists():
            return
        width = max(20, canvas.winfo_width())
        height = max(25, canvas.winfo_height())
        y = height // 2
        ratio = (self._value - self._from) / (self._to - self._from)
        x = round(10 + ratio * (width - 20))
        canvas.delete("all")
        canvas.configure(bg=parent_bg(self))
        # Inset four-pixel track; XP's slider track is neutral, not a progress bar.
        canvas.create_rectangle(8, y - 2, width - 8, y + 2, fill="#d4d0c8", outline="#808080")
        canvas.create_line(9, y - 1, width - 9, y - 1, fill="#ffffff")
        border = T.BUTTON_HOT_BORDER if self._hot or self._focused else T.SUCCESS
        canvas.create_polygon(x - 6, y - 10, x + 6, y - 10, x + 6, y + 5,
                              x, y + 10, x - 6, y + 5, fill="#ffffff", outline=border, width=1)
        canvas.create_line(x - 4, y - 8, x + 4, y - 8, fill="#d7f1d0")


def slider(parent, from_: int, to: int, command=None, width: int = 260) -> XPSlider:
    return XPSlider(parent, from_, to, command=command, width=width)


def parent_bg(widget) -> str:
    w = getattr(widget, "master", None)
    while w is not None:
        try:
            c = w.cget("fg_color")
            if c not in ("transparent", None, ""):
                return T.resolve(c)
        except Exception:
            pass
        w = getattr(w, "master", None)
    return T.resolve(T.BG)


# ------------------------------------------------------------------ buttons
class Btn(ctk.CTkButton):
    """Luna-style command button with light faces, bevels, and a hot border."""

    STYLES = {
        "primary":      dict(fg=T.BUTTON_FACE, hover=T.BUTTON_HOVER, text=T.TEXT, border=T.ACCENT, icon=T.TEXT),
        "secondary":    dict(fg=T.BUTTON_FACE, hover=T.BUTTON_HOVER, text=T.TEXT, border=T.BORDER_STRONG, icon=T.TEXT),
        "outline":      dict(fg=T.BUTTON_FACE, hover=T.BUTTON_HOVER, text=T.TEXT, border=T.BORDER_STRONG, icon=T.TEXT),
        "danger":       dict(fg=T.DANGER, hover=T.DANGER_HOVER, text=T.ON_ACCENT, border=T.DANGER_HOVER, icon=T.ON_ACCENT),
        "ghost":        dict(fg="transparent", hover=T.ACCENT_SOFT, text=T.TEXT, border=None, icon=T.TEXT),
        "link":         dict(fg="transparent", hover="transparent", text=T.ACCENT, border=None, icon=T.ACCENT),
        "danger_ghost": dict(fg="transparent", hover=T.DANGER_SOFT, text=T.DANGER, border=None, icon=T.DANGER),
    }

    def __init__(self, master, text: str = "", variant: str = "secondary", icon: Optional[str] = None,
                 command: Optional[Callable] = None, width: int = 110, height: int = 32, anchor: str = "center",
                 size: int = 12, bold: Optional[bool] = None, radius: int = 2, icon_right: bool = False):
        st = self.STYLES[variant]
        self._st = st
        self._variant = variant
        self._enabled = True
        self._normal_border_width = 2 if variant == "primary" else (1 if st["border"] else 0)
        img = icons.icon(icon, 16, st["icon"]) if icon else None
        weight = "bold" if (bold if bold is not None else variant == "primary") else "normal"
        super().__init__(
            master, text=(f" {text}" if (img and text and not icon_right) else text) if text else "",
            image=img, compound="right" if icon_right else "left", command=command, width=width, height=height,
            corner_radius=radius, fg_color=st["fg"], hover=False, text_color=st["text"],
            text_color_disabled=T.TEXT_FAINT, border_width=self._normal_border_width,
            border_color=st["border"] or T.BORDER, font=T.font(size, weight), anchor=anchor)
        self._bevel = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=T.BUTTON_GLOSS)
        self._shadow = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=T.BUTTON_SHADOW)
        self._sync_bevel()
        self.bind("<Enter>", lambda e: self._fade(True), add="+")
        self.bind("<Leave>", lambda e: self._fade(False), add="+")
        for part in (self._bevel, self._shadow):
            part.bind("<Enter>", lambda e: self._fade(True), add="+")
            part.bind("<Leave>", lambda e: self._fade(False), add="+")
            part.bind("<ButtonRelease-1>", lambda e: self.invoke() if self._enabled else None, add="+")
            hand(part)
        hand(self)
        keyboard_button(self, self._normal_border_width)

    def _sync_bevel(self) -> None:
        if self._variant in ("primary", "secondary", "outline"):
            self._bevel.configure(fg_color=T.BUTTON_GLOSS)
            self._bevel.place(relx=0.02, y=3, relwidth=0.96)
            self._shadow.place(relx=0.02, rely=1, y=-4, relwidth=0.96)
        else:
            self._bevel.place_forget()
            self._shadow.place_forget()

    def _fade(self, entering: bool) -> None:
        if not self._enabled or self._variant == "link":
            if self._variant == "link" and self._enabled:
                self.configure(text_color=self._st.get("hover_text", T.ACCENT_HOVER) if entering else self._st["text"])
            return
        if self._variant in ("primary", "secondary", "outline", "danger"):
            self.configure(fg_color=self._st["hover"] if entering else self._st["fg"],
                           border_color=(T.BUTTON_HOT_BORDER if entering and self._variant != "danger"
                                         else self._st["border"]))
            return
        base, hov = self._st["fg"], self._st["hover"]
        bg = parent_bg(self)
        a = bg if base == "transparent" else T.resolve(base)
        b = T.resolve(hov)
        cur_target = (a, b) if entering else (b, a)
        end = hov if entering else base
        tween_color(self, "fg_color", cur_target[0], cur_target[1], 130, final=end, key="hover")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(state="normal" if enabled else "disabled")
        self._canvas.configure(takefocus=1 if enabled else 0)


class IconBtn(ctk.CTkButton):
    """Square icon-only button with hover tint and optional tooltip."""

    def __init__(self, master, icon_name: str, size: int = 16, box: int = 30, color=T.TEXT_MUTED,
                 hover_color=T.TEXT, hover_bg=T.SURFACE_2, command: Optional[Callable] = None,
                 tooltip: Optional[str] = None, radius: int = 2, base_bg="transparent"):
        self._icon_name, self._icon_size, self._icon_color, self._icon_hover_color = icon_name, size, color, hover_color
        self._icon_hover_bg, self._icon_base_bg = hover_bg, base_bg
        super().__init__(master, text="", image=icons.icon(icon_name, size, color), width=box, height=box,
                         corner_radius=radius, fg_color=base_bg, hover=False, command=command)
        hand(self)
        keyboard_button(self, 0)
        self.bind("<Enter>", lambda e: self._on(True), add="+")
        self.bind("<Leave>", lambda e: self._on(False), add="+")
        if tooltip:
            Tooltip(self, tooltip)

    def _on(self, entering: bool) -> None:
        self.configure(image=icons.icon(self._icon_name, self._icon_size, self._icon_hover_color if entering else self._icon_color))
        a = parent_bg(self) if self._icon_base_bg == "transparent" else T.resolve(self._icon_base_bg)
        b = T.resolve(self._icon_hover_bg)
        tween_color(self, "fg_color", a if entering else b, b if entering else a, 120,
                    final=self._icon_hover_bg if entering else self._icon_base_bg, key="hover")

    def set_icon(self, name: str, color=None) -> None:
        self._icon_name = name
        if color is not None:
            self._icon_color = color
        self.configure(image=icons.icon(name, self._icon_size, self._icon_color))


# ------------------------------------------------------------------ tooltip
class Tooltip:
    def __init__(self, widget, text: str, delay: int = 550):
        self.widget, self.text, self.delay = widget, text, delay
        self._job = None
        self._tip: Optional[tkinter.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _e=None) -> None:
        self._hide()
        self._job = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tkinter.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            try:
                tip.wm_attributes("-topmost", True)
            except tkinter.TclError:
                pass
            frame = tkinter.Frame(tip, bg=T.resolve(T.BORDER_STRONG), padx=1, pady=1)
            frame.pack()
            tkinter.Label(frame, text=self.text, bg="#ffffe1", fg="#111111",
                          font=(T.FAMILY, 9), padx=8, pady=4).pack()
            tip.update_idletasks()
            tip.wm_geometry(f"+{x - tip.winfo_reqwidth() // 2}+{y}")
            self._tip = tip
        except tkinter.TclError:
            self._tip = None

    def _hide(self, _e=None) -> None:
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tkinter.TclError:
                pass
            self._tip = None


# -------------------------------------------------------------------- field
class Field(ctk.CTkFrame):
    """Bordered text input: focus ring, optional leading icon, password eye, badge slot, readonly mode."""

    def __init__(self, master, placeholder: str = "", password: bool = False, icon: Optional[str] = None,
                 height: int = 32, width: int = 200, readonly: bool = False, font_size: int = 12):
        super().__init__(master, fg_color=T.INPUT, border_color=T.BORDER_STRONG, border_width=1, corner_radius=1,
                         height=height, width=width)
        self.pack_propagate(False)
        self._password, self._revealed, self._readonly = password, False, readonly
        self._error = False
        self._focused = False
        self._full_text = ""
        self._font = T.font(font_size)

        if icon:
            ctk.CTkLabel(self, text="", image=icons.icon(icon, 16, T.TEXT_FAINT), width=28).pack(side="left", padx=(8, 0))

        self._trail = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self._trail.pack(side="right", padx=(0, 4))
        self._badge = ctk.CTkLabel(self._trail, text="", width=1)
        self._badge_size = 0

        if readonly:
            self.entry = None
            self._label = ctk.CTkLabel(self, text="", font=self._font, text_color=T.TEXT, anchor="w")
            self._label.pack(side="left", fill="x", expand=True, padx=(12, 6))
            self.bind("<Configure>", lambda e: self._refit(), add="+")
        else:
            self.entry = ctk.CTkEntry(
                self, placeholder_text=placeholder, show="•" if password else "", fg_color="transparent",
                border_width=0, text_color=T.TEXT, placeholder_text_color=T.TEXT_FAINT, font=self._font,
                height=height - 8)
            self.entry.pack(side="left", fill="both", expand=True, padx=(12 if not icon else 4, 4), pady=2)
            self.entry.bind("<FocusIn>", lambda e: self._focus(True), add="+")
            self.entry.bind("<FocusOut>", lambda e: self._focus(False), add="+")

        if password:
            self._eye = IconBtn(self._trail, "eye", 16, 28, tooltip="Show / hide", command=self.toggle_reveal)
            self._eye.pack(side="right")
        self._inset = inset_edges(self)

    # ---- api
    def get(self) -> str:
        return self._full_text if self._readonly else self.entry.get()

    def set(self, text: str) -> None:
        if self._readonly:
            self._full_text = text or ""
            self._refit()
        else:
            e = self.entry
            if text:
                e.delete(0, "end")
                e.insert(0, text)
            elif not getattr(e, "_placeholder_text_active", False):
                # CTkEntry believes it is focused from the start, so clearing it would otherwise lose the placeholder
                e._entry.delete(0, "end")
                e._activate_placeholder()

    def focus(self) -> None:
        if self.entry is not None:
            self.entry.focus_set()

    def bind_key(self, fn: Callable) -> None:
        if self.entry is not None:
            self.entry.bind("<KeyRelease>", fn, add="+")

    def bind_return(self, fn: Callable) -> None:
        if self.entry is not None:
            self.entry.bind("<Return>", lambda e: fn(), add="+")

    def set_error(self, on: bool) -> None:
        self._error = on
        self._paint_border()

    def toggle_reveal(self, force: Optional[bool] = None) -> None:
        self._revealed = (not self._revealed) if force is None else force
        new_show = "" if self._revealed else "•"
        e = self.entry
        if getattr(e, "_placeholder_text_active", False):
            e._pre_placeholder_arguments["show"] = new_show
        else:
            e.configure(show=new_show)
        self._eye.set_icon("eye-off" if self._revealed else "eye")

    def set_badge(self, image: Optional[ctk.CTkImage], pop: bool = True) -> None:
        """Show a small logo at the right edge (used for recognised company names)."""
        if image is None:
            self._badge.pack_forget()
            self._badge_size = 0
            return
        if self._badge_size == 0:
            self._badge.pack(side="left", padx=(0, 6))
        target = image._size[0]
        self._badge_size = target
        if not pop:
            self._badge.configure(image=image)
            return
        # pop-in: 10px -> overshoot -> target
        steps = [int(target * f) for f in (0.45, 0.8, 1.15, 1.0)]
        for i, sz in enumerate(steps):
            self.after(i * 35, lambda s=sz, im=image: self._badge_frame(im, s))

    def _badge_frame(self, image, size: int) -> None:
        try:
            im = ctk.CTkImage(light_image=image._light_image, dark_image=image._dark_image, size=(size, size))
            self._badge.configure(image=im)
            self._badge._keep = im
        except Exception:
            pass

    # ---- internals
    def _refit(self) -> None:
        if not self._readonly:
            return
        avail = max(20, self.winfo_width() / T.widget_scale(self) - 60)
        self._label.configure(text=fit_text(self._full_text, self._font, avail, ellipsis_left=True))

    def _focus(self, on: bool) -> None:
        self._focused = on
        self._paint_border()

    def _paint_border(self) -> None:
        target = T.DANGER if self._error else (T.ACCENT if self._focused else T.BORDER)
        for edge in self._inset:
            T.track_tk_color(edge, target if self._error or self._focused else T.BORDER_STRONG)
        try:
            cur = T.resolve(self.cget("border_color"))
        except Exception:
            cur = T.resolve(T.BORDER)
        tween_color(self, "border_color", cur, T.resolve(target), 120, final=target, key="border")

    def destroy(self) -> None:
        cancel_owned_after_jobs(self)
        super().destroy()


# -------------------------------------------------------------------- popup
class Popup:
    """One floating panel at a time, drawn inside the anchor's window (no OS windows involved)."""

    current: Optional["Popup"] = None

    def __init__(self, anchor, build: Callable[[ctk.CTkFrame], None], min_width: int = 0, align: str = "left",
                 match_anchor: bool = False):
        self.anchor, self.build, self.min_width, self.align = anchor, build, min_width, align
        self.match_anchor = match_anchor
        self.frame: Optional[ctk.CTkFrame] = None
        self._buttons: list[ctk.CTkButton] = []
        self._focus_index = 0

    @classmethod
    def close_current(cls) -> None:
        if cls.current is not None:
            cls.current.close()

    @staticmethod
    def _hook(top) -> None:
        if getattr(top, "_popup_hooked", False):
            return
        top._popup_hooked = True

        def on_click(e):
            p = Popup.current
            if p is None:
                return
            w = str(e.widget)
            if w.startswith(str(p.frame)) or w.startswith(str(p.anchor)):
                return
            p.close()

        top.bind("<Button-1>", on_click, add="+")
        top.bind("<Escape>", lambda e: Popup.close_current(), add="+")
        top.bind("<Configure>", lambda e: Popup.close_current() if e.widget is top else None, add="+")

    def open(self) -> None:
        Popup.close_current()
        top = self.anchor.winfo_toplevel()
        self._hook(top)
        f = ctk.CTkFrame(top, fg_color=T.SURFACE, border_width=1, border_color=T.BORDER_STRONG, corner_radius=0)
        self.frame = f
        self.build(f)
        top.update_idletasks()
        s = T.widget_scale(f)
        req_w = max(f.winfo_reqwidth(), int(self.min_width * s), self.anchor.winfo_width() if self.match_anchor else 0)
        req_h = f.winfo_reqheight()
        ax = self.anchor.winfo_rootx() - top.winfo_rootx()
        ay = self.anchor.winfo_rooty() - top.winfo_rooty()
        aw, ah = self.anchor.winfo_width(), self.anchor.winfo_height()
        x = ax + aw - req_w if self.align == "right" else ax
        x = max(8, min(x, top.winfo_width() - req_w - 8))
        y = ay + ah + 1
        if y + req_h > top.winfo_height() - 8 and ay - 6 - req_h > 8:
            y = ay - 6 - req_h
        f.pack_propagate(False)
        f.configure(width=req_w / s, height=req_h / s)
        f.place(x=x / s, y=y / s)
        f.tkraise()
        Popup.current = self
        self._buttons = [w for w in f.winfo_children() if isinstance(w, ctk.CTkButton)]
        for index, button in enumerate(self._buttons):
            button._xp_base_fg = button.cget("fg_color")
            button._xp_base_text = button.cget("text_color")
            button._xp_base_image = button.cget("image")
            button.configure(hover_color=T.MENU_SELECT)
            button.bind("<Down>", lambda e, i=index: self._focus(i + 1), add="+")
            button.bind("<Up>", lambda e, i=index: self._focus(i - 1), add="+")
            button.bind("<Return>", lambda e, b=button: (b.invoke(), "break")[1], add="+")
            button.bind("<space>", lambda e, b=button: (b.invoke(), "break")[1], add="+")
            button.bind("<Enter>", lambda e, i=index: self._focus(i), add="+")
        if self._buttons:
            self._focus(0)

    def _focus(self, index: int) -> str:
        if not self._buttons:
            return "break"
        self._focus_index = index % len(self._buttons)
        for i, button in enumerate(self._buttons):
            selected = i == self._focus_index
            icon_name = getattr(button, "_xp_icon_name", None)
            button.configure(border_width=0,
                             fg_color=T.MENU_SELECT if selected else button._xp_base_fg,
                             text_color=T.ON_ACCENT if selected else button._xp_base_text,
                             image=(icons.icon(icon_name, 14, T.ON_ACCENT) if selected and icon_name
                                    else button._xp_base_image))
        button = self._buttons[self._focus_index]
        target = getattr(button, "_text_label", None) or getattr(button, "_label", None) or button
        target.focus_set()
        return "break"

    def close(self) -> None:
        if Popup.current is self:
            Popup.current = None
        if self.frame is not None:
            try:
                self.frame.destroy()
            except tkinter.TclError:
                pass
            self.frame = None
        self._buttons.clear()
        try:
            if self.anchor.winfo_exists():
                self.anchor.focus_set()
        except tkinter.TclError:
            pass

    @property
    def is_open(self) -> bool:
        return self.frame is not None


class Dropdown(ctk.CTkFrame):
    def __init__(self, master, options: Sequence[Option], value: Optional[str] = None,
                 command: Optional[Callable[[str], None]] = None, width: int = 160, height: int = 32,
                 icon: Optional[str] = None, enabled: bool = True):
        super().__init__(master, fg_color=T.INPUT, border_color=T.BORDER_STRONG, border_width=1, corner_radius=1,
                         width=width, height=height)
        self._canvas.configure(takefocus=1 if enabled else 0)
        self._canvas.bind("<FocusIn>", lambda e: self.configure(border_width=2, border_color=T.ACCENT), add="+")
        self._canvas.bind("<FocusOut>", lambda e: self.configure(border_width=1, border_color=T.BORDER_STRONG), add="+")
        self.pack_propagate(False)
        self._opts: List[Option] = list(options)
        self._value = value if value is not None else (self._opts[0][0] if self._opts else None)
        self._command, self._enabled, self._width = command, enabled, width
        self._popup: Optional[Popup] = None
        if icon:
            self._icon = ctk.CTkLabel(self, text="", image=icons.icon(icon, 16, T.TEXT_FAINT), width=24)
            self._icon.pack(side="left", padx=(10, 0))
        self._chev = ctk.CTkLabel(self, text="", image=icons.icon("chevron-down", 16, T.TEXT_MUTED), width=24)
        self._chev.pack(side="right", padx=(0, 8))
        self._text = ctk.CTkLabel(self, text=self.label(), font=T.font(12), text_color=T.TEXT, anchor="w")
        self._text.pack(side="left", fill="x", expand=True, padx=(12 if not icon else 6, 2))
        for w in (self, self._text, self._chev):
            w.bind("<Button-1>", self._toggle, add="+")
            w.bind("<Enter>", lambda e: self._hover(True), add="+")
            w.bind("<Leave>", lambda e: self._hover(False), add="+")
            w.bind("<Return>", self._key_toggle, add="+")
            w.bind("<space>", self._key_toggle, add="+")
            w.bind("<Alt-Down>", self._key_toggle, add="+")
        if enabled:
            hand(self); hand(self._text); hand(self._chev)
        else:
            self._text.configure(text_color=T.TEXT_MUTED)
            self._chev.configure(image=icons.icon("chevron-down", 16, T.TEXT_FAINT))
        self._inset = inset_edges(self)

    def focus_set(self):
        return self._canvas.focus_set()

    def label(self) -> str:
        return next((l for k, l in self._opts if k == self._value), "")

    def get(self) -> Optional[str]:
        return self._value

    def set(self, key: str) -> None:
        self._value = key
        self._text.configure(text=self.label())

    def set_options(self, options: Sequence[Option], value: Optional[str] = None) -> None:
        self._opts = list(options)
        if value is not None:
            self._value = value
        if self._value not in [k for k, _ in self._opts] and self._opts:
            self._value = self._opts[0][0]
        self._text.configure(text=self.label())

    def _hover(self, on: bool) -> None:
        if not self._enabled:
            return
        a, b = T.resolve(T.BORDER), T.resolve(T.BORDER_STRONG)
        tween_color(self, "border_color", a if on else b, b if on else a, 110,
                    final=T.BORDER_STRONG if on else T.BORDER, key="border")

    def _toggle(self, _e=None) -> None:
        if not self._enabled:
            return
        if self._popup is not None and self._popup.is_open and Popup.current is self._popup:
            self._popup.close()
            return
        self._popup = Popup(self, self._build_menu, min_width=self._width, match_anchor=True)
        self._popup.open()

    def _key_toggle(self, _e=None) -> str:
        self._toggle()
        return "break"

    def _build_menu(self, frame: ctk.CTkFrame) -> None:
        for key, label in self._opts:
            selected = key == self._value
            b = ctk.CTkButton(
                frame, text=label, anchor="w", height=32, corner_radius=1, fg_color=T.ACCENT_SOFT if selected else "transparent",
                hover_color=T.SURFACE_2, text_color=T.TEXT if selected else T.TEXT_MUTED, font=T.font(13),
                image=icons.icon("check", 14, T.ACCENT) if selected else None, compound="right",
                command=lambda k=key: self._choose(k))
            b._xp_icon_name = "check" if selected else None
            b.pack(fill="x", padx=4, pady=(4 if key == self._opts[0][0] else 1, 4 if key == self._opts[-1][0] else 1))
            hand(b)

    def _choose(self, key: str) -> None:
        Popup.close_current()
        changed = key != self._value
        self.set(key)
        if changed and self._command:
            self._command(key)


def open_menu(anchor, items: list, align: str = "right", min_width: int = 170) -> Popup:
    """Context menu. items: dict(label, icon, command, danger) or None for a separator."""
    def build(frame):
        for it in items:
            if it is None:
                divider(frame).pack(fill="x", padx=8, pady=3)
                continue
            danger = it.get("danger", False)
            b = ctk.CTkButton(
                frame, text=" " + it["label"], anchor="w", height=26, corner_radius=0, fg_color="transparent",
                hover_color=T.DANGER_SOFT if danger else T.SURFACE_2, text_color=T.DANGER if danger else T.TEXT,
                font=T.font(12), image=icons.icon(it["icon"], 14, T.DANGER if danger else T.TEXT_MUTED), compound="left",
                command=lambda c=it["command"]: (Popup.close_current(), c()))
            b._xp_icon_name = it["icon"]
            b.pack(fill="x", padx=4, pady=1)
            hand(b)
        ctk.CTkFrame(frame, height=3, fg_color="transparent").pack()
    menu = Popup(anchor, build, min_width=min_width, align=align)
    menu.open()
    return menu


# ----------------------------------------------------------- strength meter
class StrengthMeter(ctk.CTkFrame):
    def __init__(self, master, segments: int = 6, show_label: bool = True, label_width: int = 90):
        super().__init__(master, fg_color="transparent")
        self._n = segments
        self._filled = 0
        self._segs = []
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="left", fill="x", expand=True)
        for i in range(segments):
            bar.grid_columnconfigure(i, weight=1, uniform="seg")
            s = ctk.CTkFrame(bar, width=1, height=7, corner_radius=0, fg_color=T.BORDER_STRONG)
            s.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
            self._segs.append(s)
        self._label = ctk.CTkLabel(self, text="", font=T.font(13, "bold"), text_color=T.SUCCESS,
                                   width=label_width, anchor="e") if show_label else None
        if self._label:
            self._label.pack(side="right", padx=(12, 0))

    def set(self, bits: float, label: str = "") -> None:
        import math
        filled = 0 if bits <= 0 else min(self._n, max(1, math.ceil(bits / (110.0 / self._n))))
        frac = filled / self._n
        color = T.DANGER if frac <= 0.34 else (T.WARNING if frac <= 0.5 else T.SUCCESS)
        for i, seg in enumerate(self._segs):
            want = color if i < filled else T.BORDER_STRONG
            was_on = i < self._filled
            now_on = i < filled
            if was_on != now_on or (now_on and i < filled):
                cur = T.resolve(seg.cget("fg_color"))
                self.after(i * 25, lambda s=seg, c=cur, w=want: tween_color(s, "fg_color", c, T.resolve(w), 160, final=w, key="fill"))
        self._filled = filled
        if self._label:
            self._label.configure(text=label, text_color=color)

    def destroy(self) -> None:
        cancel_owned_after_jobs(self)
        super().destroy()


# -------------------------------------------------------------------- toasts
class Toasts:
    """Slide-in notifications, bottom-right of the window, auto-dismiss."""

    W, H, GAP, MARGIN = 360, 72, 10, 22

    def __init__(self, root):
        self.root = root
        self._items: list = []
        self._resize_job = None
        root.bind("<Configure>", self._on_configure, add="+")

    def show(self, title: str, message: str = "", kind: str = "success", duration: int = 3200) -> None:
        icon_name = {"success": "circle-check", "info": "clipboard-check", "error": "circle-x", "copy": "clipboard-check"}.get(kind, "circle-check")
        accent = {"success": T.SUCCESS, "info": T.ACCENT, "copy": T.SUCCESS, "error": T.DANGER}.get(kind, T.SUCCESS)
        soft = {"success": T.SUCCESS_SOFT, "info": T.ACCENT_SOFT, "copy": T.SUCCESS_SOFT, "error": T.DANGER_SOFT}.get(kind, T.SUCCESS_SOFT)
        while len(self._items) >= 3:
            self._dismiss(self._items[0], instant=True)

        f = ctk.CTkFrame(self.root, width=self.W, height=self.H, fg_color=T.SURFACE, border_width=1,
                         border_color=T.BORDER_STRONG, corner_radius=2)
        f.pack_propagate(False)
        ctk.CTkFrame(f, width=3, fg_color=accent, corner_radius=0).pack(side="left", fill="y", pady=1)
        disc = ctk.CTkFrame(f, width=38, height=38, corner_radius=2, fg_color=soft)
        disc.pack(side="left", padx=(12, 12))
        disc.pack_propagate(False)
        ctk.CTkLabel(disc, text="", image=icons.icon(icon_name, 20, accent)).place(relx=0.5, rely=0.5, anchor="center")
        col = ctk.CTkFrame(f, fg_color="transparent")
        col.pack(side="left", fill="both", expand=True, pady=12)
        ctk.CTkLabel(col, text=title, font=T.font(13, "bold"), text_color=T.TEXT, anchor="w").pack(fill="x")
        if message:
            ctk.CTkLabel(col, text=fit_text(message, T.font(12), self.W - 118), font=T.font(12),
                         text_color=T.TEXT_MUTED, anchor="w").pack(fill="x")
        item = {"frame": f, "y": 0.0, "job": None}
        IconBtn(f, "x", 14, 26, command=lambda: self._dismiss(item)).pack(side="right", padx=(0, 10), anchor="n", pady=8)
        self._items.append(item)
        self._layout(animate_new=item)
        item["job"] = f.after(duration, lambda: self._dismiss(item))

    def clear(self) -> None:
        """Remove every toast immediately (used when the vault locks)."""
        for it in list(self._items):
            self._dismiss(it, instant=True)

    def _target(self, index: int) -> Tuple[float, float]:
        s = T.widget_scale(self.root)
        rw, rh = self.root.winfo_width() / s, self.root.winfo_height() / s
        x = rw - self.W - self.MARGIN
        y = rh - self.MARGIN - (self.H + self.GAP) * (len(self._items) - index) + self.GAP
        return x, y

    def _layout(self, animate_new=None) -> None:
        for i, it in enumerate(self._items):
            x, y = self._target(i)
            f = it["frame"]
            if it is animate_new:
                f.place(x=x + 60, y=y)
                f.tkraise()
                animate(f, "in", 220, lambda t, f=f, x=x, y=y: f.place(x=x + 60 * (1 - t), y=y))
            else:
                it["y"] = y
                f.place(x=x, y=y)
                f.tkraise()
            it["y"] = y

    def _dismiss(self, item, instant: bool = False) -> None:
        if item not in self._items:
            return
        self._items.remove(item)
        f = item["frame"]
        if item.get("job"):
            try:
                f.after_cancel(item["job"])
            except Exception:
                pass

        def kill() -> None:
            try:
                f.destroy()
            except tkinter.TclError:
                pass
            self._layout()

        if instant:
            kill()
            return
        try:
            x0 = float(f.place_info().get("x", 0)) / T.widget_scale(self.root)
            y0 = float(f.place_info().get("y", 0)) / T.widget_scale(self.root)
        except Exception:
            kill()
            return
        animate(f, "out", 170, lambda t: f.place(x=x0 + 70 * t, y=y0), done=kill)

    def _on_configure(self, e) -> None:
        if e.widget is not self.root or not self._items:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(60, self._layout)
