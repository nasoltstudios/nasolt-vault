"""
paths.py — where the app finds its bundled assets and where it keeps user data.

* resource_path(): read-only files shipped with the app (icons, brand logos).
  Works from source, and inside a PyInstaller bundle (sys._MEIPASS).
* data_dir(): the writable folder holding vault.enc and settings.json.

Data-folder rules (so an installed copy under "C:\\Program Files" doesn't crash):
  1. NASOLT_DATA_DIR environment variable (used by tests / power users)
  2. an existing ./data/vault.enc next to the app  (keeps every existing vault working)
  3. ./data next to the app, if that folder is writable and the app was NOT set up by the installer (portable mode)
  4. %APPDATA%\\Nasolt Vault\\data  (installed copy — the installer drops an `installed.flag` file — or a read-only folder)
"""
from __future__ import annotations

import os
import sys

FROZEN: bool = bool(getattr(sys, "frozen", False))
APP_DIR: str = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))

_cache: dict[str, str] = {}


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or APP_DIR
    return os.path.join(base, *parts)


def _is_writable(folder: str) -> bool:
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write_test")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def is_installed() -> bool:
    """True when this copy was put in place by the Windows installer (it writes installed.flag next to the exe)."""
    return os.path.isfile(os.path.join(APP_DIR, "installed.flag"))


def data_dir() -> str:
    override = os.environ.get("NASOLT_DATA_DIR", "")
    key = override or "__default__"
    if key in _cache:
        return _cache[key]

    if override:
        os.makedirs(override, exist_ok=True)
        result = override
    else:
        legacy = os.path.join(APP_DIR, "data")
        if os.path.isfile(os.path.join(legacy, "vault.enc")) or (not is_installed() and _is_writable(legacy)):
            result = legacy
        else:
            root = os.environ.get("APPDATA") or os.path.expanduser("~")
            result = os.path.join(root, "Nasolt Vault", "data")
            os.makedirs(result, exist_ok=True)
    _cache[key] = result
    return result


def default_export_dir() -> str:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    base = docs if os.path.isdir(docs) else os.path.expanduser("~")
    return os.path.join(base, "NasoltVault")
