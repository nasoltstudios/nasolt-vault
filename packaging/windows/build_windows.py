"""
build.py — builds the single-file, windowed "Nasolt Vault" program with PyInstaller.

    python build.py            (or just double-click BUILD_WINDOWS.bat, which does everything for you)

Safety checks (added after a build shipped without one of its libraries and crashed on start-up):
  1. BEFORE building, every pinned runtime library must already be installed for THIS Python.
  2. AFTER building, the finished program is started in a hidden self-test (--selftest) that imports every
     library, checks every bundled icon and does a real encrypt / decrypt. The build is only reported
     as successful if that passes.

PyInstaller cannot cross-compile: run this on Windows to get a Windows .exe.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(ROOT, "src")
ASSETS = os.path.join(SOURCE, "nasolt_vault", "assets")
OUTPUT = os.path.join(ROOT, "packaging", "windows", "artifacts")
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
        print("\nBUILD STOPPED — still missing: " + ", ".join(missing))
        print("Install the pinned build and runtime requirements first:")
        print(f'     "{sys.executable}" -m pip install -r packaging/requirements.txt')
        print(f'     "{sys.executable}" -m pip install -r packaging/requirements-build.txt')
        return False
    return True


def self_test(exe: str) -> bool:
    print("\nSelf-testing the built program (checks libraries, icons and encryption) …")
    fd, report = tempfile.mkstemp(prefix="nasolt_build_selftest_", suffix=".txt")
    os.close(fd)
    try:
        env = dict(os.environ, NASOLT_SELFTEST_REPORT=report)
        try:
            code = subprocess.call([exe, "--selftest"], timeout=180, env=env)
        except subprocess.TimeoutExpired:
            code = -1
        with open(report, encoding="utf-8") as result:
            text = result.read() or "(the program did not write a report — it crashed on start)"
    finally:
        os.unlink(report)
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

    os.makedirs(os.path.join(OUTPUT, "spec"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT, "dist"), exist_ok=True)
    exe = os.path.join(OUTPUT, "dist", NAME + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(exe):
        os.remove(exe)  # avoid accepting an old executable after an incomplete build

    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", NAME,
        "--distpath", os.path.join(OUTPUT, "dist"),
        "--workpath", os.path.join(OUTPUT, "build"),
        "--specpath", os.path.join(OUTPUT, "spec"),
        "--paths", SOURCE,
        "--add-data", f"{ASSETS}{SEP}nasolt_vault/assets",  # package icons and app icon pack
        "--collect-all", "customtkinter",            # its themes / fonts
        "--hidden-import", "PIL._tkinter_finder",    # Pillow <-> Tk bridge (needed for the images)
        "--hidden-import", "argon2", "--hidden-import", "argon2.low_level",
        "--hidden-import", "cryptography.hazmat.primitives.ciphers.aead",
        "--hidden-import", "cryptography.hazmat.bindings._rust",
        "--exclude-module", "tools",
    ]
    ico = os.path.join(ASSETS, "app.ico")
    if os.path.exists(ico):
        cmd += ["--icon", ico]
    cmd.append(os.path.join(SOURCE, "nasolt_vault", "__main__.py"))

    print("\nBuilding …  (this takes a minute or two)\n")
    code = subprocess.call(cmd)
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
