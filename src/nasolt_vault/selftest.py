"""
selftest.py — headless packaging check.   `Nasolt Vault.exe --selftest`

build.py runs this on the freshly built program so a broken build (a missing library, a missing icon,
a broken encryption module) is reported at build time instead of crashing on your desktop.
Only the standard library is imported at the top, so it can still report when third-party modules are missing.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import traceback

REPORT = os.environ.get("NASOLT_SELFTEST_REPORT") or os.path.join(tempfile.gettempdir(), "nasolt_vault_selftest.txt")

THIRD_PARTY = ["tkinter", "_tkinter", "customtkinter", "darkdetect", "PIL", "PIL.ImageTk", "PIL._tkinter_finder",
               "cryptography", "cryptography.hazmat.primitives.ciphers.aead", "argon2", "argon2.low_level", "pyperclip"]
APP_MODULES = ["paths", "crypto", "vault", "export", "generators", "clipboard", "app_settings", "icons", "ui.theme",
               "ui.anim", "ui.widgets", "ui.modal", "ui.entry_dialog", "ui.vault_page", "ui.groups_page",
               "ui.generator_page", "ui.transfer_page", "ui.settings_page", "ui.login", "ui.shell",
               "lockout_lab", "ui.lockout_lab_page", "quick_access", "windows_shortcuts",
               "ui.summon_popup", "ui.reauth_prompt", "instance",
               "windows_startup", "windows_tray", "windows_focus", "windows_hello",
               "hello_enrollment"]
ASSETS = [("assets", "app.ico"), ("assets", "app.png"),
          ("assets", "app_icons", "nasolt-vault-16.png"), ("assets", "app_icons", "nasolt-vault-512.png"),
          ("assets", "brands.json"), ("assets", "icons", "lock.png"),
          ("assets", "icons", "search.png")]


def run() -> int:
    # PyInstaller's windowed bootloader supplies no console streams. Some GUI
    # dependencies write a startup warning while importing, even headlessly.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    lines: list[str] = []
    ok = True

    def fail(msg: str) -> None:
        nonlocal ok
        ok = False
        lines.append("FAIL  " + msg)

    data = tempfile.mkdtemp(prefix="nasolt_selftest_")
    os.environ["NASOLT_DATA_DIR"] = data

    for name in THIRD_PARTY:
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001
            fail(f"library '{name}' is missing from the program ({type(e).__name__}: {e})")
    for name in APP_MODULES:
        try:
            importlib.import_module(f"nasolt_vault.{name}")
        except Exception as e:  # noqa: BLE001
            fail(f"app module '{name}' failed to load ({type(e).__name__}: {e})")

    try:
        from .paths import resource_path
        for parts in ASSETS:
            p = resource_path(*parts)
            if not os.path.isfile(p):
                fail("bundled file missing: " + "/".join(parts))
    except Exception as e:  # noqa: BLE001
        fail(f"could not check assets ({e})")

    try:  # real encryption round trip (catches broken Argon2 / cryptography binaries)
        from .vault import VaultSession
        s = VaultSession()
        s.create("selftest-Passw0rd!")
        s.save([{"id": "1", "title": "x", "password": "synthetic-selftest-only"}], [])
        s.close()
        reopened = VaultSession()
        try:
            entries, _ = reopened.open("selftest-Passw0rd!")
        finally:
            reopened.close()
        if entries[0]["title"] != "x":
            fail("encryption round trip returned wrong data")
        wrong = VaultSession()
        try:
            try:
                wrong.open("wrong-password")
                fail("wrong password was accepted")
            except ValueError:
                pass
        finally:
            wrong.close()
    except Exception:  # noqa: BLE001
        fail("encryption round trip crashed:\n" + traceback.format_exc())

    shutil.rmtree(data, ignore_errors=True)
    lines.insert(0, "SELFTEST " + ("PASSED" if ok else "FAILED"))
    try:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass
    try:
        print("\n".join(lines))
    except Exception:  # windowed builds have no console
        pass
    return 0 if ok else 1
