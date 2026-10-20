"""
build.py — builds the single-file, windowed "Nasolt Vault" program with PyInstaller.

    python build.py            (or just double-click BUILD_WINDOWS.bat, which does everything for you)

Safety checks (added after a build shipped without one of its libraries and crashed on start-up):
  1. BEFORE building, every library the app needs must be importable by THIS Python; missing ones are
     installed automatically from requirements.txt.
  2. AFTER building, the finished program is started in a hidden self-test (--selftest) that imports every
     library, checks every bundled icon and does a real encrypt / decrypt. The build is only reported
     as successful if that passes.

PyInstaller cannot cross-compile: run this on Windows to get a Windows .exe.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "Nasolt Vault"
SEP = ";" if os.name == "nt" else ":"
REQUIRED = [("customtkinter", "customtkinter"), ("darkdetect", "darkdetect"), ("PIL", "Pillow"),
            ("cryptography", "cryptography"), ("argon2", "argon2-cffi"), ("pyperclip", "pyperclip")]


def missing_libraries() -> list[str]:
    return [pkg for mod, pkg in REQUIRED if importlib.util.find_spec(mod) is None]


def ensure_libraries() -> bool:
    print(f"Python used for this build: {sys.executable}  ({sys.version.split()[0]})")
    missing = missing_libraries()
    if missing:
        print(f"\nThese libraries are not installed for this Python: {', '.join(missing)}")
        print("Installing them now from requirements.txt …\n")
        subprocess.call([sys.executable, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")])
        importlib.invalidate_caches()
        missing = missing_libraries()
    if missing:
        print("\nBUILD STOPPED — still missing: " + ", ".join(missing))
        print("Fix: double-click BUILD_WINDOWS.bat (it creates a clean environment for you), or run:")
        print(f'     "{sys.executable}" -m pip install -r requirements.txt')
        return False
    return True


def self_test(exe: str) -> bool:
    print("\nSelf-testing the built program (checks libraries, icons and encryption) …")
    report = os.path.join(tempfile.gettempdir(), "nasolt_vault_selftest.txt")
    if os.path.exists(report):
        os.remove(report)
    try:
        code = subprocess.call([exe, "--selftest"], timeout=180)
    except subprocess.TimeoutExpired:
        code = -1
    text = open(report, encoding="utf-8").read() if os.path.exists(report) else "(the program did not write a report — it crashed on start)"
    print(text)
    return code == 0 and text.startswith("SELFTEST PASSED")


def main() -> int:
    os.chdir(ROOT)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed for this Python.  Run:  pip install pyinstaller")
        return 1
    if not ensure_libraries():
        return 1

    for folder in ("build", "dist"):
        shutil.rmtree(folder, ignore_errors=True)
    if os.path.exists(f"{NAME}.spec"):
        os.remove(f"{NAME}.spec")

    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", NAME,
        "--paths", ROOT,
        "--add-data", f"assets{SEP}assets",          # UI icons and original app icon pack
        "--collect-all", "customtkinter",            # its themes / fonts
        "--hidden-import", "PIL._tkinter_finder",    # Pillow <-> Tk bridge (needed for the images)
        "--hidden-import", "argon2", "--hidden-import", "argon2.low_level",
        "--hidden-import", "cryptography.hazmat.primitives.ciphers.aead",
        "--hidden-import", "cryptography.hazmat.bindings._rust",
        "--exclude-module", "tools",
    ]
    ico = os.path.join("assets", "app.ico")
    if os.path.exists(ico):
        cmd += ["--icon", ico]
    cmd.append("main.py")

    print("\nBuilding …  (this takes a minute or two)\n")
    code = subprocess.call(cmd)
    exe = os.path.join(ROOT, "dist", NAME + (".exe" if os.name == "nt" else ""))
    if code != 0 or not os.path.exists(exe):
        print("\nBUILD FAILED — scroll up for the PyInstaller error.")
        return code or 1
    if not self_test(exe):
        print("\n" + "=" * 60 + "\nBUILD FAILED — the program was built but did not pass its self-test (details above).\n" + "=" * 60)
        return 1
    print("\n" + "=" * 60 + f"\nBUILD SUCCESSFUL (self-test passed)\n   {exe}\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
