"""Recoverable, per-user installer file replacement. Never opens vault data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from . import installer_shortcuts as ownership

EXE = ownership.EXE
UNINSTALL = ownership.UNINSTALL
MARKER = "installed.flag"
JOURNAL = ".nasolt-install-transaction.json"
STAGED = {EXE: ".nasolt-next-app.exe", UNINSTALL: ".nasolt-next-uninstall.exe",
          MARKER: ".nasolt-next-marker"}
PREVIOUS = {EXE: ".nasolt-previous-app.exe", UNINSTALL: ".nasolt-previous-uninstall.exe"}
CANDIDATE = {EXE: "NasoltShortcutCheck.exe", UNINSTALL: UNINSTALL, MARKER: MARKER}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class UpgradeConflict(Exception):
    """Stop without replacing a file whose ownership or bytes are uncertain."""


def _regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and not path.is_junction()


def _hash(path: Path) -> str:
    if not _regular(path):
        raise UpgradeConflict("A required program file is missing or linked")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_exclusive(source: Path, target: Path, expected: str) -> None:
    if target.exists() or target.is_symlink():
        raise UpgradeConflict("A reserved installer recovery file already exists")
    try:
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if _hash(target) != expected:
            raise UpgradeConflict("A staged program file failed byte verification")
    except Exception:
        if _regular(target):
            target.unlink()
        raise


def _journal_path(folder: Path) -> Path:
    return folder / JOURNAL


def _read_journal(folder: Path) -> dict:
    path = _journal_path(folder)
    if not _regular(path) or path.stat().st_size > 4096:
        raise UpgradeConflict("Installer recovery journal is missing or invalid")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        raise UpgradeConflict("Installer recovery journal is invalid") from None
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("kind") not in ("new", "upgrade")
            or not isinstance(data.get("install_dir"), str)
            or not ownership._same_path(data.get("install_dir", ""), str(folder))):
        raise UpgradeConflict("Installer recovery journal does not match this folder")
    if not isinstance(data.get("new"), dict) or not isinstance(data.get("previous"), dict):
        raise UpgradeConflict("Installer recovery journal has invalid file lists")
    for name in (EXE, UNINSTALL, MARKER):
        value = data["new"].get(name)
        if not isinstance(value, str) or not _HASH.fullmatch(value):
            raise UpgradeConflict("Installer recovery journal has invalid file hashes")
    if data["kind"] == "upgrade":
        for name in (EXE, UNINSTALL, MARKER):
            value = data["previous"].get(name)
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                raise UpgradeConflict("Installer recovery journal has invalid backup hashes")
    return data


def _write_journal(folder: Path, data: dict) -> None:
    temporary = folder / (JOURNAL + ".new")
    if temporary.exists() or temporary.is_symlink() or _journal_path(folder).exists():
        raise UpgradeConflict("Installer recovery files already exist")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump(data, output, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    os.rename(temporary, _journal_path(folder))


def _remove_if_expected(path: Path, expected: str) -> None:
    if path.exists() or path.is_symlink():
        if _hash(path) != expected:
            raise UpgradeConflict("An installation file changed during recovery")
        path.unlink()


def _clear_recovery_files(folder: Path, data: dict) -> None:
    # The journal is removed first: after verification, the program is either
    # committed or restored. Orphaned copies never affect the running app.
    removable: list[tuple[Path, str]] = []
    for name, saved in PREVIOUS.items():
        old_hash = data["previous"].get(name)
        if old_hash:
            removable.append((folder / saved, old_hash))
    for name, staged in STAGED.items():
        removable.append((folder / staged, data["new"][name]))
    for path, expected in removable:
        if (path.exists() or path.is_symlink()) and _hash(path) != expected:
            raise UpgradeConflict("Installer recovery files changed")
    _journal_path(folder).unlink()
    for path, expected in removable:
        _remove_if_expected(path, expected)


def rollback(folder: Path) -> None:
    data = _read_journal(folder)
    if data["kind"] == "upgrade":
        if not ownership._same_path(ownership._registered_install_dir() or "", str(folder)):
            raise UpgradeConflict("Upgrade registration changed during recovery")
        for name, saved in PREVIOUS.items():
            old_hash = data["previous"][name]
            if _hash(folder / saved) != old_hash:
                raise UpgradeConflict("A previous program copy is missing or damaged")
            current = folder / name
            if (current.exists() or current.is_symlink()) and _hash(current) not in (old_hash, data["new"][name]):
                raise UpgradeConflict("An installation file changed during recovery")
        for name, saved in PREVIOUS.items():
            current = folder / name
            if not current.exists() or _hash(current) != data["previous"][name]:
                temporary = folder / STAGED[name]
                _remove_if_expected(temporary, data["new"][name])
                _copy_exclusive(folder / saved, temporary, data["previous"][name])
                os.replace(temporary, current)
    else:
        registered = ownership._registered_install_dir()
        if registered and not ownership._same_path(registered, str(folder)):
            raise UpgradeConflict("A different installation is registered")
        for name in (EXE, UNINSTALL, MARKER):
            current = folder / name
            if current.exists() or current.is_symlink():
                if _hash(current) != data["new"][name]:
                    raise UpgradeConflict("An installation file changed during recovery")
        for name in (EXE, UNINSTALL, MARKER):
            _remove_if_expected(folder / name, data["new"][name])
    _clear_recovery_files(folder, data)


def recover(folder: Path) -> None:
    if folder.is_symlink() or folder.is_junction():
        raise UpgradeConflict("Installation folder is linked")
    if _journal_path(folder).exists() or _journal_path(folder).is_symlink():
        rollback(folder)


def install(folder: Path, candidates: Path) -> None:
    if not candidates.is_dir() or candidates.is_symlink() or candidates.is_junction():
        raise UpgradeConflict("Installer candidate directory is unavailable")
    new_hashes = {name: _hash(candidates / candidate) for name, candidate in CANDIDATE.items()}
    try:
        ownership._check_install_dir(folder)
    except ownership.ShortcutConflict as exc:
        raise UpgradeConflict(str(exc)) from None
    if not folder.exists():
        folder.mkdir(parents=True)
    kind = "upgrade" if any(folder.iterdir()) else "new"
    if kind == "upgrade":
        # The registered program must be complete before any staged write.
        try:
            ownership._check_install_dir(folder, uninstall=True)
        except ownership.ShortcutConflict as exc:
            raise UpgradeConflict(str(exc)) from None
    reserved = [folder / JOURNAL, folder / (JOURNAL + ".new"),
                *(folder / p for p in STAGED.values()), *(folder / p for p in PREVIOUS.values())]
    if any(path.exists() or path.is_symlink() for path in reserved):
        raise UpgradeConflict("Unresolved installer recovery files are present")
    previous = {name: _hash(folder / name) for name in (EXE, UNINSTALL, MARKER)} if kind == "upgrade" else {}
    data = {"version": 1, "kind": kind, "install_dir": str(folder),
            "new": new_hashes, "previous": previous}
    created: list[Path] = []
    journal_written = False
    try:
        for name, saved in PREVIOUS.items():
            if kind == "upgrade":
                target = folder / saved
                _copy_exclusive(folder / name, target, previous[name])
                created.append(target)
        for name, staged in STAGED.items():
            if kind == "upgrade" and name == MARKER:
                continue
            target = folder / staged
            _copy_exclusive(candidates / CANDIDATE[name], target, new_hashes[name])
            created.append(target)
        for name in PREVIOUS:
            if kind == "upgrade" and _hash(folder / name) != previous[name]:
                raise UpgradeConflict("A program file changed during staging")
        _write_journal(folder, data)
        journal_written = True
        for name in (EXE, UNINSTALL, MARKER):
            if kind == "upgrade" and name == MARKER:
                continue
            source, target = folder / STAGED[name], folder / name
            if kind == "new":
                if target.exists() or target.is_symlink():
                    raise UpgradeConflict("A file appeared in the installation folder")
                os.rename(source, target)  # Windows refuses an existing target.
            else:
                if _hash(target) != previous[name]:
                    raise UpgradeConflict("A program file changed during installation")
                os.replace(source, target)
            if _hash(target) != new_hashes[name]:
                raise UpgradeConflict("An installed program file failed verification")
    except Exception:
        if journal_written:
            rollback(folder)
        else:
            for path in created:
                if _regular(path):
                    path.unlink()
            temporary = folder / (JOURNAL + ".new")
            if _regular(temporary):
                temporary.unlink()
        raise


def finalize(folder: Path) -> None:
    data = _read_journal(folder)
    for name in (EXE, UNINSTALL, MARKER):
        expected = data["previous"][MARKER] if data["kind"] == "upgrade" and name == MARKER else data["new"][name]
        if _hash(folder / name) != expected:
            raise UpgradeConflict("Installation is incomplete; recovery is available")
    if not ownership._same_path(ownership._registered_install_dir() or "", str(folder)):
        raise UpgradeConflict("Install registration was not written")
    command = ownership._registered_uninstaller()
    if not command or not ownership._same_path(command.strip().strip('"'), str(folder / UNINSTALL)):
        raise UpgradeConflict("Uninstall registration was not written")
    _clear_recovery_files(folder, data)


def cli(args: list[str]) -> int:
    if sys.platform != "win32" or len(args) not in (2, 3):
        return 3
    mode, folder = args[:2]
    try:
        if mode == "recover" and len(args) == 2:
            recover(Path(folder))
        elif mode == "install" and len(args) == 3:
            install(Path(folder), Path(args[2]))
        elif mode == "rollback" and len(args) == 2:
            rollback(Path(folder))
        elif mode == "finalize" and len(args) == 2:
            finalize(Path(folder))
        else:
            return 3
        return 0
    except UpgradeConflict as exc:
        if sys.stderr is not None:
            print(f"Nasolt Vault setup stopped: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        if sys.stderr is not None:
            print(f"Nasolt Vault setup failed ({type(exc).__name__}); rerun setup to recover", file=sys.stderr)
        return 3
