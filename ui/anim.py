"""anim.py — tiny tween engine for subtle, cheap animations (after()-driven, ~60 fps)."""
from __future__ import annotations

import time
import tkinter
from typing import Callable, Optional


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return "#%02x%02x%02x" % (round(ar + (br - ar) * t), round(ag + (bg - ag) * t), round(ab + (bb - ab) * t))


def animate(widget, key: str, duration_ms: int, step: Callable[[float], None],
            done: Optional[Callable[[], None]] = None, ease: Callable[[float], float] = ease_out) -> None:
    """Run step(t) for t: 0->1 over duration. A new animation with the same key replaces the old one."""
    if "_anims" not in widget.__dict__:
        widget.__dict__["_anims"] = {}
        widget.bind("<Destroy>", lambda event: cancel_all(widget)
                    if event.widget in (widget, getattr(widget, "_canvas", None)) else None, add="+")
    anims = widget.__dict__["_anims"]
    old = anims.pop(key, None)
    if old is not None:
        try:
            widget.after_cancel(old)
        except Exception:
            pass
    start = time.perf_counter()

    def tick() -> None:
        try:
            if not widget.winfo_exists():
                return
            t = (time.perf_counter() - start) * 1000.0 / max(1, duration_ms)
            if t >= 1.0:
                anims.pop(key, None)
                step(1.0)
                if done:
                    done()
                return
            step(ease(t))
            anims[key] = widget.after(14, tick)
        except tkinter.TclError:
            anims.pop(key, None)

    anims[key] = widget.after(1, tick)


def cancel(widget, key: str) -> None:
    anims = widget.__dict__.get("_anims", {})
    aid = anims.pop(key, None)
    if aid is not None:
        try:
            widget.after_cancel(aid)
        except Exception:
            pass


def cancel_all(widget) -> None:
    """Remove pending Tk callbacks before a control is destroyed."""
    anims = widget.__dict__.get("_anims", {})
    for aid in list(anims.values()):
        try:
            widget.after_cancel(aid)
        except Exception:
            pass
    anims.clear()


def cancel_owned_after_jobs(widget) -> None:
    """Cancel pending Tk callbacks registered through a widget before it is destroyed."""
    commands = set(widget._tclCommands or [])
    try:
        for job in widget.tk.call("after", "info"):
            script = widget.tk.call("after", "info", job)[0]
            if str(script).split()[0] in commands:
                widget.after_cancel(job)
    except tkinter.TclError:
        pass


def cancel_tree_after_jobs(widget) -> None:
    """Cancel callbacks owned by a page and its controls before removing its Tk tree."""
    try:
        children = widget.winfo_children()
    except tkinter.TclError:
        children = ()
    for child in children:
        cancel_tree_after_jobs(child)
    cancel_owned_after_jobs(widget)


def tween_color(widget, prop: str, a: str, b: str, duration_ms: int = 140, final=None, key: Optional[str] = None) -> None:
    """Animate widget.configure(prop=colour) from hex a to hex b, then set `final` (e.g. the adaptive tuple)."""
    def step(t: float) -> None:
        try:
            widget.configure(**{prop: lerp_hex(a, b, t)})
        except tkinter.TclError:
            pass

    def done() -> None:
        if final is not None:
            try:
                widget.configure(**{prop: final})
            except tkinter.TclError:
                pass

    animate(widget, key or f"color:{prop}", duration_ms, step, done)
