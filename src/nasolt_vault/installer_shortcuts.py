"""Conservative ownership checks for per-user installer shortcuts.

The installer calls this before creating links and before uninstalling.  Link
inspection never launches a target.  Ambiguous links stop the operation.
"""
from __future__ import annotations

import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
import tempfile


APP = "Nasolt Vault"
EXE = "Nasolt Vault.exe"
UNINSTALL = "Uninstall.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NasoltVault"


class ShortcutConflict(Exception):
    pass


def _same_path(left: str, right: str) -> bool:
    return bool(left and right) and ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def _registered_install_dir() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
        return value if isinstance(value, str) else None
    except OSError:
        return None


def _registered_uninstaller() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "UninstallString")
        return value if isinstance(value, str) else None
    except OSError:
        return None


def _check_install_dir(install_dir: Path, *, uninstall: bool = False) -> None:
    """Refuse to replace an unrelated folder or remove an unowned install."""
    if install_dir.is_symlink() or install_dir.is_junction():
        raise ShortcutConflict("Installation folder is a link")
    registered = _registered_install_dir()
    if registered and not _same_path(registered, str(install_dir)):
        raise ShortcutConflict("A different Nasolt Vault installation is registered")
    if not install_dir.exists():
        if uninstall:
            raise ShortcutConflict("Installation folder is missing")
        return
    if not install_dir.is_dir():
        raise ShortcutConflict("Installation path is not a directory")
    pending = install_dir / ".nasolt-install-transaction.json"
    if pending.exists() or pending.is_symlink():
        raise ShortcutConflict("An installer transaction must be recovered first")
    if not uninstall and not any(install_dir.iterdir()):
        return
    marker = install_dir / "installed.flag"
    executable = install_dir / EXE
    uninstaller = install_dir / UNINSTALL
    if not registered or not _same_path(registered, str(install_dir)):
        raise ShortcutConflict("Nonempty installation folder is not registered")
    if any(path.is_symlink() or path.is_junction() or not path.is_file()
           for path in (marker, executable, uninstaller)):
        raise ShortcutConflict("Installation marker or program files are missing or linked")
    command = _registered_uninstaller()
    if not command or not _same_path(command.strip().strip('"'), str(uninstaller)):
        raise ShortcutConflict("Uninstall registration does not belong to this folder")


def _link_details(link: Path) -> dict[str, str] | None:
    if link.is_symlink() or not link.is_file():
        return None
    env = os.environ.copy()
    env["NASOLT_INSTALLER_LINK"] = str(link)
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:NASOLT_INSTALLER_LINK); "
              "@{target=$s.TargetPath; arguments=$s.Arguments; workdir=$s.WorkingDirectory; "
              "icon=$s.IconLocation; hotkey=$s.Hotkey} | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=15, check=False)
        details = json.loads(result.stdout) if result.returncode == 0 else None
        keys = ("target", "arguments", "workdir", "icon", "hotkey")
        return details if isinstance(details, dict) and all(isinstance(details.get(k), str) for k in keys) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _owned(details: dict[str, str], target: Path, install_dir: Path) -> bool:
    """Accept links created by this installer and by the previous NSIS version.

    Old NSIS links may have empty workdir/icon or Shell-generated target icons.
    A changed command, icon, working directory, or hotkey is ambiguous.
    """
    if not all(isinstance(details.get(key), str) for key in ("target", "arguments", "workdir", "icon", "hotkey")):
        return False
    icon = details["icon"].strip()
    if "," in icon and icon.rsplit(",", 1)[-1].lstrip("-").isdigit():
        icon = icon.rsplit(",", 1)[0]
    return (_same_path(details["target"], str(target))
            and not details["arguments"].strip()
            and (not details["workdir"] or _same_path(details["workdir"], str(install_dir)))
            and (not icon or _same_path(icon, str(target)))
            and not details["hotkey"].strip())


def _links(install_dir: Path, programs_dir: Path, desktop_dir: Path) -> dict[str, tuple[Path, Path]]:
    menu = programs_dir / APP
    return {
        "main": (menu / f"{APP}.lnk", install_dir / EXE),
        "uninstall": (menu / f"Uninstall {APP}.lnk", install_dir / UNINSTALL),
        "desktop": (desktop_dir / f"{APP}.lnk", install_dir / EXE),
    }


def _check(mode: str, install_dir: Path, programs_dir: Path, desktop_dir: Path) -> list[tuple[Path, Path, bool]]:
    menu = programs_dir / APP
    if menu.is_symlink() or menu.is_junction() or (menu.exists() and not menu.is_dir()):
        raise ShortcutConflict("Start Menu folder is not an ordinary directory")
    known_install = ((install_dir / "installed.flag").is_file()
                     and _same_path(_registered_install_dir() or "", str(install_dir)))
    names = ("main", "uninstall") if mode in ("check-main", "install-main") else (
        ("desktop",) if mode in ("check-desktop", "install-desktop") else
        ("main", "uninstall", "desktop"))
    result = []
    for name in names:
        link, target = _links(install_dir, programs_dir, desktop_dir)[name]
        present = link.exists() or link.is_symlink()
        if present:
            details = _link_details(link)
            if not known_install or details is None or not _owned(details, target, install_dir):
                raise ShortcutConflict(f"Cannot verify ownership of {link}")
        result.append((link, target, present))
    return result


def _create(link: Path, target: Path, install_dir: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    # Recheck immediately before Save; never ask COM to open a preexisting
    # shortcut that was not part of the verified installation.
    if link.exists() or link.is_symlink():
        raise ShortcutConflict(f"Shortcut appeared while installing: {link}")
    fd, temp_name = tempfile.mkstemp(prefix=".nasolt-link-", suffix=".lnk", dir=link.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        env = os.environ.copy()
        env.update({"NASOLT_INSTALLER_LINK": str(temp), "NASOLT_INSTALLER_TARGET": str(target),
                    "NASOLT_INSTALLER_WORKDIR": str(install_dir)})
        script = ("$ErrorActionPreference='Stop'; "
                  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:NASOLT_INSTALLER_LINK); "
                  "$s.TargetPath=$env:NASOLT_INSTALLER_TARGET; "
                  "$s.Arguments=''; $s.WorkingDirectory=$env:NASOLT_INSTALLER_WORKDIR; "
                  "$s.IconLocation=$env:NASOLT_INSTALLER_TARGET; $s.Hotkey=''; $s.Save()")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, timeout=15, check=False)
        if result.returncode != 0 or not _owned(_link_details(temp) or {}, target, install_dir):
            raise OSError(f"Could not create and verify {link}")
        # On Windows rename refuses an existing destination. COM never opens
        # the final path, even if another process creates it mid-install.
        os.rename(temp, link)
    finally:
        temp.unlink(missing_ok=True)


def manage(mode: str, install_dir: Path, programs_dir: Path, desktop_dir: Path) -> None:
    if mode not in {"check-install-dir", "check-uninstall", "check-main", "install-main",
                    "check-desktop", "install-desktop", "uninstall"}:
        raise ValueError("Unknown shortcut operation")
    if mode in {"check-install-dir", "check-uninstall"}:
        _check_install_dir(install_dir, uninstall=mode == "check-uninstall")
        return
    links = _check(mode, install_dir, programs_dir, desktop_dir)
    if mode.startswith("check"):
        return
    if mode == "uninstall":
        for link, target, present in links:
            if present:
                # Link contents might have changed since the first check.
                if not _owned(_link_details(link) or {}, target, install_dir):
                    raise ShortcutConflict(f"Shortcut changed during uninstall: {link}")
                link.unlink()
        menu = programs_dir / APP
        if menu.is_dir() and not any(menu.iterdir()):
            menu.rmdir()
        return
    for link, target, present in links:
        if not present:
            _create(link, target, install_dir)


def cli(args: list[str]) -> int:
    if sys.platform != "win32" or len(args) != 4:
        return 3
    mode, install, programs, desktop = args
    try:
        manage(mode, Path(install), Path(programs), Path(desktop))
        return 0
    except ShortcutConflict as exc:
        if sys.stderr is not None:
            print(f"Nasolt Vault installer shortcut conflict: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        if sys.stderr is not None:
            print(f"Nasolt Vault installer shortcut operation failed: {type(exc).__name__}", file=sys.stderr)
        return 3
