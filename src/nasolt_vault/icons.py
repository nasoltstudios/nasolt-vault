"""
icons.py — offline icons.

* ui icon(name, size, color)  — white line-icon masks in assets/icons, tinted at runtime.
* optional brand images      — local images only when redistribution is allowed.
* entry_icon(title, url)     — uses an original offline brand monogram when a
                               known account matches, otherwise a bank glyph
                               or coloured initial avatar.
Nothing here touches the network.
"""
from __future__ import annotations

import colorsys
import json
import os
import re
from typing import Dict, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from .paths import resource_path
from .ui import theme

_masks: Dict[str, Image.Image] = {}
_images: Dict[tuple, ctk.CTkImage] = {}
_app_logo: Optional[Image.Image] = None
_manifest: Optional[dict] = None
_alias_map: Dict[str, str] = {}
_domain_map: Dict[str, str] = {}


# ------------------------------------------------------------ UI line icons
def reset_tk_cache() -> None:
    """CTkImage creates Tk photos tied to one root; discard them before a new root."""
    _images.clear()


def app_logo(size: int = 36) -> ctk.CTkImage:
    """The Nasolt lock mark, cached for use in the app chrome."""
    global _app_logo
    key = ("app-logo", size)
    if key not in _images:
        if _app_logo is None:
            with Image.open(resource_path("assets", "app.png")) as source:
                _app_logo = source.convert("RGBA")
        _images[key] = ctk.CTkImage(light_image=_app_logo, dark_image=_app_logo, size=(size, size))
    return _images[key]


def _mask(name: str) -> Image.Image:
    if name not in _masks:
        _masks[name] = Image.open(resource_path("assets", "icons", f"{name}.png")).convert("RGBA")
    return _masks[name]


def _tint(name: str, hex_color: str) -> Image.Image:
    mask = _mask(name)
    solid = Image.new("RGBA", mask.size, hex_color)
    solid.putalpha(mask.getchannel("A"))
    return solid


def icon(name: str, size: int = 18, color=theme.TEXT_MUTED) -> ctk.CTkImage:
    key = ("ui", name, size, color if not isinstance(color, list) else tuple(color))
    if key not in _images:
        light, dark = (color if isinstance(color, (tuple, list)) else (color, color))
        _images[key] = ctk.CTkImage(light_image=_tint(name, light), dark_image=_tint(name, dark), size=(size, size))
    return _images[key]


# --------------------------------------------------------------- brand data
def _load_manifest() -> dict:
    global _manifest
    if _manifest is None:
        try:
            with open(resource_path("assets", "brands.json"), "r", encoding="utf-8") as f:
                _manifest = json.load(f)
        except (OSError, ValueError):
            _manifest = {"brands": {}, "generic": {}}
        for slug, info in _manifest["brands"].items():
            for a in info.get("aliases", []) + [info["name"]]:
                _alias_map[_norm(a)] = slug
            for d in info.get("domains", []):
                _domain_map[d.lower()] = slug
    return _manifest


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _host(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u)
    host = re.split(r"[/?#:]", u, maxsplit=1)[0]
    return host[4:] if host.startswith("www.") else host


def match_brand(title: str, url: str = "") -> Optional[str]:
    """Return a brand slug (e.g. 'github') for a typed company name / website, else None."""
    m = _load_manifest()
    t = _norm(title)
    if t:
        if t in _alias_map:
            return _alias_map[t]
        for tok in t.split():
            if len(tok) >= 3 and tok in _alias_map:
                return _alias_map[tok]
        squashed = t.replace(" ", "")
        if squashed in _alias_map:
            return _alias_map[squashed]
    host = _host(url)
    if host:
        for domain, slug in _domain_map.items():
            if host == domain or host.endswith("." + domain):
                return slug
    return None


def is_bank(title: str) -> bool:
    m = _load_manifest()
    padded = f" {_norm(title)} "
    return any(f" {_norm(k)} " in padded for k in m.get("generic", {}).get("bank", []))


def brand_name(slug: str) -> str:
    return _load_manifest()["brands"].get(slug, {}).get("name", slug)


def brand_image(slug: str, size: int = 28) -> Optional[ctk.CTkImage]:
    key = ("brand", slug, size)
    if key in _images:
        return _images[key]
    base = resource_path("assets", "brands", f"{slug}.png")
    if not os.path.isfile(base):
        # Previous bundled logos had unclear redistribution rights. Keep account
        # recognition visible with original, locally drawn monogram tiles.
        name = brand_name(slug)
        parts = re.findall(r"[A-Z][a-z]*|[a-z]+|[0-9]+", name)
        initials = ("".join(part[0] for part in parts[:2]) if len(parts) > 1
                    else (parts[0][:2] if parts else "?")).upper()
        hue = (sum((i + 1) * ord(c) for i, c in enumerate(slug)) * 29 % 360) / 360.0
        rgb = tuple(int(v * 255) for v in colorsys.hls_to_rgb(hue, 0.38, 0.50))
        im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((2, 2, 125, 125), radius=18, fill=rgb + (255,), outline=(67, 75, 86, 255), width=3)
        draw.line((11, 18, 117, 18), fill=(255, 255, 255, 155), width=3)
        font = _avatar_font(56 if len(initials) == 2 else 70)
        box = draw.textbbox((0, 0), initials, font=font)
        x = (128 - (box[2] - box[0])) / 2 - box[0]
        y = (128 - (box[3] - box[1])) / 2 - box[1]
        draw.text((x, y), initials, font=font, fill=(255, 255, 255, 255), stroke_width=1,
                  stroke_fill=(26, 42, 68, 255))
        _images[key] = ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))
        return _images[key]
    dark_path = resource_path("assets", "brands", f"{slug}_dark.png")
    light_img = Image.open(base).convert("RGBA")
    dark_img = Image.open(dark_path).convert("RGBA") if os.path.isfile(dark_path) else light_img
    _images[key] = ctk.CTkImage(light_image=light_img, dark_image=dark_img, size=(size, size))
    return _images[key]


# ---------------------------------------------------------- avatar fallback
def _avatar_font(px: int):
    for name in ("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


def avatar_image(text: str, size: int = 28) -> ctk.CTkImage:
    letter = next((c for c in (text or "?") if c.isalnum()), "?").upper()
    hue = (sum(ord(c) for c in (text or "?").lower()) * 37 % 360) / 360.0
    key = ("avatar", letter, hue, size)
    if key not in _images:
        r, g, b = [int(v * 255) for v in colorsys.hls_to_rgb(hue, 0.48, 0.45)]
        px = 128
        im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((0, 0, px - 1, px - 1), fill=(r, g, b, 255))
        f = _avatar_font(68)
        try:
            box = d.textbbox((0, 0), letter, font=f)
            w, h = box[2] - box[0], box[3] - box[1]
            d.text(((px - w) / 2 - box[0], (px - h) / 2 - box[1]), letter, font=f, fill=(255, 255, 255, 255))
        except Exception:
            pass
        _images[key] = ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))
    return _images[key]


def entry_icon(title: str, url: str = "", size: int = 28, recognized_only: bool = False) -> Optional[ctk.CTkImage]:
    """Best icon for an entry. With recognized_only=True returns None unless a real brand/bank matched."""
    slug = match_brand(title, url)
    if slug:
        img = brand_image(slug, size)
        if img is not None:
            return img
    if is_bank(title):
        return icon("landmark", size, theme.TEXT)
    if recognized_only:
        return None
    if (title or "").strip():
        return avatar_image(title, size)
    return icon("globe", size, theme.TEXT_MUTED)
