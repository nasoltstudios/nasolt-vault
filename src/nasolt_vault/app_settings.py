"""
app_settings.py — lightweight, unencrypted local preferences (settings.json).

Never stores anything secret: only UI preferences such as auto-lock delay
and the chosen export folder. Legacy theme values are ignored by the UI.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

from .paths import data_dir

DEFAULTS: Dict[str, Any] = {
    "export_dir": "",          # "" = use the default ~/Documents/NasoltVault
    "autolock_minutes": 15,
    "summon_shortcut": "ctrl+alt+n",
    "summon_timeout_seconds": 30,
    "start_with_windows": True,
    "close_to_tray": True,
    "cold_start_shortcuts": False,
}


def settings_file() -> str:
    return os.path.join(data_dir(), "settings.json")


def load_settings() -> Dict[str, Any]:
    merged = dict(DEFAULTS)
    try:
        with open(settings_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged.update({key: value for key, value in data.items()
                           if key not in ("theme", "voicekey_shortcut")})
    except (OSError, ValueError):
        pass
    return merged


def save_settings(settings: Dict[str, Any]) -> None:
    tmp = None
    try:
        target = settings_file()
        folder = os.path.dirname(target)
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".nasolt-settings-", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({key: value for key, value in settings.items()
                       if key != "voicekey_shortcut"}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except OSError:
        pass  # preferences are best-effort; never crash the app over them
    finally:
        if tmp is not None and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def get(key: str, default: Any = None) -> Any:
    s = load_settings()
    return s[key] if key in s else default


def set_value(key: str, value: Any) -> None:
    s = load_settings()
    s[key] = value
    save_settings(s)


def get_export_dir() -> str:
    return load_settings().get("export_dir", "") or ""


def set_export_dir(path: str) -> None:
    set_value("export_dir", path)
