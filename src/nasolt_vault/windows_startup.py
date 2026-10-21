"""Per-user Windows sign-in registration. Isolated test data never changes HKCU."""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

from .paths import APP_DIR, SOURCE_CHECKOUT, resource_path

VALUE_NAME = "Nasolt Vault"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--background"]
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        executable = pythonw if os.path.isfile(pythonw) else sys.executable
        command = [executable, "-m", "nasolt_vault", "--background"]
    return subprocess.list2cmdline(command)


def _legacy_source_commands() -> set[str]:
    if not SOURCE_CHECKOUT or getattr(sys, "frozen", False):
        return set()
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    executable = pythonw if os.path.isfile(pythonw) else sys.executable
    old_venv = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
    return {subprocess.list2cmdline([target, os.path.join(APP_DIR, "main.py"), "--background"])
            for target in (executable, old_venv)}


def sync_startup(enabled: bool, *, isolated: bool | None = None) -> str:
    if sys.platform != "win32":
        return "Windows only"
    if isolated is None:
        isolated = "NASOLT_DATA_DIR" in os.environ
    if isolated:
        return "isolated test mode"
    import winreg
    command = launch_command() if enabled else ""
    if enabled and len(command) > 260:
        return "startup command exceeds Windows Run limit"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current, _ = winreg.QueryValueEx(key, VALUE_NAME)
            except FileNotFoundError:
                current = None
            # Never replace or remove a same-named value written by another
            # program (or by an installation we can no longer identify).
            if current is not None and current not in ({launch_command()} | _legacy_source_commands()):
                return "unowned startup entry"
            if enabled:
                if current != command:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
                return "enabled"
            if current is not None:
                # This uniquely named value is managed by Nasolt Vault.
                winreg.DeleteValue(key, VALUE_NAME)
            return "disabled"
    except OSError:
        return "unavailable"


def _link_folder(programs_dir=None) -> Path:
    root = Path(programs_dir) if programs_dir else Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return root / "Nasolt Vault"


def _launch_target(route: str) -> tuple[str, str, str]:
    if getattr(sys, "frozen", False):
        return sys.executable, f"--{route}", os.path.dirname(sys.executable)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    target = pythonw if os.path.isfile(pythonw) else sys.executable
    args = subprocess.list2cmdline(["-m", "nasolt_vault", f"--{route}"])
    return target, args, APP_DIR


def _legacy_launch_target(route: str) -> tuple[str, str, str] | None:
    if not SOURCE_CHECKOUT or getattr(sys, "frozen", False):
        return None
    target, _, _ = _launch_target(route)
    return target, subprocess.list2cmdline([os.path.join(APP_DIR, "main.py"), f"--{route}"]), APP_DIR


def _legacy_launch_targets(route: str) -> list[tuple[str, str, str]]:
    current = _legacy_launch_target(route)
    if current is None:
        return []
    old_venv = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
    return [current, (old_venv, current[1], APP_DIR)]


def _shortcut_details(link: Path) -> dict[str, str] | None:
    """Read a Shell link without executing it; unknown links are never deleted."""
    if link.is_symlink() or not link.is_file():
        return None
    env = os.environ.copy()
    env["NASOLT_LINK_PATH"] = str(link)
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "$ErrorActionPreference='Stop'; "
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:NASOLT_LINK_PATH); "
              "@{target=$s.TargetPath; arguments=$s.Arguments; workdir=$s.WorkingDirectory; "
              "icon=$s.IconLocation} | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=10, check=False)
        details = json.loads(result.stdout) if result.returncode == 0 else None
        return details if isinstance(details, dict) and all(
            isinstance(details.get(key), str) for key in ("target", "arguments", "workdir", "icon")) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _owned_shortcut(details: dict[str, str], route: str) -> bool:
    """Recognize only links pointing to this running installation."""
    target, arguments, workdir = _launch_target(route)
    icon = details["icon"].strip()
    if icon.rsplit(",", 1)[-1].isdigit():
        icon = icon.rsplit(",", 1)[0]
    normalized = lambda value: os.path.normcase(os.path.normpath(value))
    current = (target, arguments, workdir, resource_path("assets", "app.ico"))
    candidates = [current]
    candidates.extend((*legacy, os.path.join(APP_DIR, "assets", "app.ico"))
                      for legacy in _legacy_launch_targets(route))
    return any(normalized(details["target"]) == normalized(t)
               and details["arguments"].strip().casefold() == a.casefold()
               and normalized(details["workdir"]) == normalized(w)
               and normalized(icon) == normalized(i)
               for t, a, w, i in candidates)


def _remove_owned_link(link: Path, route: str) -> bool:
    if not link.exists() and not link.is_symlink():
        return True
    details = _shortcut_details(link)
    if details is None:
        return False
    if not _owned_shortcut(details, route):
        return True  # A user-created link with the same name is left intact.
    try:
        link.unlink()
        return True
    except OSError:
        return False


def cleanup_legacy_voice_link(*, isolated: bool | None = None, programs_dir=None) -> str:
    """Remove only the old app-owned V shortcut, including on legacy --voice launch."""
    if sys.platform != "win32":
        return "Windows only"
    if isolated is None:
        isolated = "NASOLT_DATA_DIR" in os.environ
    if isolated:
        return "isolated test mode"
    folder = _link_folder(programs_dir)
    if not _remove_owned_link(folder / "Nasolt VoiceKey.lnk", "voice"):
        return "unavailable"
    try:
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        return "unavailable"
    return "removed"


def sync_cold_start_links(enabled: bool, *, isolated: bool | None = None, programs_dir=None) -> str:
    """Install/remove per-user Shell hotkeys; these never carry vault secrets."""
    if sys.platform != "win32":
        return "Windows only"
    if isolated is None:
        isolated = "NASOLT_DATA_DIR" in os.environ
    if isolated:
        return "isolated test mode"
    folder = _link_folder(programs_dir)
    summon = folder / "Nasolt Vault Summon.lnk"
    if cleanup_legacy_voice_link(isolated=False, programs_dir=programs_dir) != "removed":
        return "unavailable"
    if not enabled:
        try:
            if not _remove_owned_link(summon, "summon"):
                return "unavailable"
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
            return "disabled"
        except OSError:
            return "unavailable"
    if not os.path.isfile(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                       "System32", "WindowsPowerShell", "v1.0", "powershell.exe")):
        return "PowerShell unavailable"
    if not _remove_owned_link(summon, "summon") or summon.exists():
        return "unavailable"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target, arguments, workdir = _launch_target("summon")
        env = os.environ.copy()
        env.update({"NASOLT_LINK_PATH": str(summon), "NASOLT_LINK_TARGET": target,
                    "NASOLT_LINK_ARGS": arguments, "NASOLT_LINK_WORKDIR": workdir,
                    "NASOLT_LINK_HOTKEY": "CTRL+ALT+N",
                    "NASOLT_LINK_ICON": resource_path("assets", "app.ico")})
        script = ("$w=New-Object -ComObject WScript.Shell; "
                  "$s=$w.CreateShortcut($env:NASOLT_LINK_PATH); "
                  "$s.TargetPath=$env:NASOLT_LINK_TARGET; "
                  "$s.Arguments=$env:NASOLT_LINK_ARGS; "
                  "$s.WorkingDirectory=$env:NASOLT_LINK_WORKDIR; "
                  "$s.Hotkey=$env:NASOLT_LINK_HOTKEY; "
                  "$s.IconLocation=$env:NASOLT_LINK_ICON; $s.Save()")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, timeout=15, check=False)
        if result.returncode != 0 or not summon.is_file():
            sync_cold_start_links(False, isolated=False, programs_dir=programs_dir)
            return "unavailable"
        return "enabled"
    except (OSError, subprocess.TimeoutExpired):
        sync_cold_start_links(False, isolated=False, programs_dir=programs_dir)
        return "unavailable"
