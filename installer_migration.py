"""Encrypted portable-vault migration used by the Windows installer.

This module never decrypts a vault. It copies one structurally recognizable
encrypted file into an empty installed-vault slot, then verifies exact bytes.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from crypto import VAULT_FILE_HEADER_LEN, read_vault_header


class MigrationError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


SOURCE_INVALID = 10
SOURCE_BUSY = 11
DESTINATION_EXISTS = 12
UNSAFE_PATH = 13
COPY_FAILED = 14
SOURCE_CHANGED = 15
BAD_ARGUMENTS = 16
SETTINGS_FAILED = 17


def installed_data_dir() -> Path:
    """The installer's fixed target, independent of portable data-dir rules."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise MigrationError(UNSAFE_PATH, "Windows APPDATA is unavailable.")
    return Path(appdata, "Nasolt Vault", "data")


def _reject_reparse_components(path: Path) -> None:
    for component in (path, *path.parents):
        if not os.path.lexists(component):
            continue
        info = os.lstat(component)
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
            raise MigrationError(UNSAFE_PATH, "A selected path uses a link or junction; no vault was copied.")


def _digest_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


@contextmanager
def _source_lock(source: Path):
    """Respect a Phase 1B portable app's lock if its lock file exists."""
    lock_path = Path(str(source) + ".lock")
    if not lock_path.exists():
        yield
        return
    try:
        lock_file = lock_path.open("r+b")
    except OSError as exc:
        raise MigrationError(SOURCE_BUSY, "The source vault lock cannot be checked.") from exc
    try:
        try:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MigrationError(SOURCE_BUSY, "The source vault is open in another app instance.") from exc
        try:
            yield
        finally:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def migrate_vault(source_dir: str | os.PathLike[str], destination_dir: str | os.PathLike[str]) -> Path:
    """Migrate ciphertext only. Never replace a destination or remove a source."""
    source = Path(os.path.abspath(source_dir), "vault.enc")
    destination_folder = Path(os.path.abspath(destination_dir))
    destination = destination_folder / "vault.enc"
    staged: Path | None = None
    try:
        _reject_reparse_components(source)
        _reject_reparse_components(Path(str(source) + ".lock"))
        _reject_reparse_components(destination)
        if source == destination:
            raise MigrationError(DESTINATION_EXISTS, "Source and installed vault are the same file.")
        if destination.exists():
            raise MigrationError(DESTINATION_EXISTS, "An installed vault already exists; it was not replaced.")
        if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
            raise MigrationError(SOURCE_INVALID, "The selected folder has no readable regular vault file.")
        with _source_lock(source):
            try:
                with source.open("rb") as stream:
                    header = stream.read(VAULT_FILE_HEADER_LEN + 1)
                read_vault_header(header)
                if len(header) <= VAULT_FILE_HEADER_LEN:
                    raise ValueError("Empty ciphertext")
                original_hash = _digest_file(source)
            except (OSError, ValueError) as exc:
                raise MigrationError(SOURCE_INVALID, "The source vault is unreadable or has an unsupported header.") from exc

            destination_folder.mkdir(parents=True, exist_ok=True)
            _reject_reparse_components(destination)
            if destination.exists():
                raise MigrationError(DESTINATION_EXISTS, "An installed vault appeared during migration.")
            fd, temp_name = tempfile.mkstemp(prefix=".nasolt-migration-", suffix=".tmp", dir=destination_folder)
            staged = Path(temp_name)
            try:
                with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
                    for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if _digest_file(staged) != original_hash or _digest_file(source) != original_hash:
                    raise MigrationError(SOURCE_CHANGED, "Source or staged ciphertext changed; no vault was installed.")
                _reject_reparse_components(destination)
                if destination.exists():
                    raise MigrationError(DESTINATION_EXISTS, "An installed vault appeared during migration.")
                # Windows rename refuses an existing destination. On POSIX, link
                # provides the same exclusive-create behavior for script tests.
                if sys.platform == "win32":
                    os.rename(staged, destination)
                else:
                    os.link(staged, destination)
                    staged.unlink()
                staged = None
                if _digest_file(destination) != original_hash:
                    raise MigrationError(COPY_FAILED, "Installed ciphertext did not verify; keep the source vault.")
                return destination
            finally:
                if staged is not None:
                    try:
                        staged.unlink()
                    except OSError:
                        pass
    except MigrationError:
        raise
    except FileExistsError as exc:
        raise MigrationError(DESTINATION_EXISTS, "An installed vault already exists; it was not replaced.") from exc
    except OSError as exc:
        raise MigrationError(COPY_FAILED, "Migration could not finish; the source vault was kept.") from exc


def _migrate_optional_file(source_dir: str | os.PathLike[str], destination_dir: str | os.PathLike[str], name: str) -> None:
    """Copy an optional data file by verified bytes, without replacing a target."""
    if name not in {"settings.json", "vault.enc.bak", "lockout_lab.enc", "lockout_lab.enc.bak"}:
        raise ValueError("Unsupported optional migration file")
    source = Path(os.path.abspath(source_dir), name)
    destination_folder = Path(os.path.abspath(destination_dir))
    destination = destination_folder / name
    staged: Path | None = None
    try:
        _reject_reparse_components(source)
        _reject_reparse_components(destination)
        if not source.exists():
            return
        if destination.exists():
            if name == "settings.json" or _digest_file(source) == _digest_file(destination):
                return
            raise MigrationError(SETTINGS_FAILED, "An installed optional encrypted file already exists.")
        if not stat.S_ISREG(source.stat().st_mode):
            raise MigrationError(SETTINGS_FAILED, "An optional source file is not a regular file.")
        original_hash = _digest_file(source)
        fd, temp_name = tempfile.mkstemp(prefix=".nasolt-settings-", suffix=".tmp", dir=destination_folder)
        staged = Path(temp_name)
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if _digest_file(staged) != original_hash or _digest_file(source) != original_hash:
            raise MigrationError(SETTINGS_FAILED, "An optional source file changed during migration.")
        _reject_reparse_components(destination)
        if sys.platform == "win32":
            os.rename(staged, destination)
        else:
            os.link(staged, destination)
            staged.unlink()
        staged = None
        if _digest_file(destination) != original_hash:
            raise MigrationError(SETTINGS_FAILED, "An optional installed file did not verify.")
    except FileExistsError:
        if name == "settings.json":
            return  # Installed settings win; never replace them.
        raise MigrationError(SETTINGS_FAILED, "An optional installed encrypted file appeared during migration.")
    except MigrationError:
        raise
    except OSError as exc:
        raise MigrationError(SETTINGS_FAILED, "Optional file migration could not finish.") from exc
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except OSError:
                pass


def migrate_settings(source_dir: str | os.PathLike[str], destination_dir: str | os.PathLike[str]) -> None:
    _migrate_optional_file(source_dir, destination_dir, "settings.json")


def cli(source_dir: str | None) -> int:
    """Return only a status code for NSIS; never print paths or file contents."""
    if not source_dir or sys.platform != "win32":
        return BAD_ARGUMENTS
    try:
        destination = installed_data_dir()
        migrate_vault(source_dir, destination)
    except MigrationError as exc:
        return exc.code
    try:
        migrate_settings(source_dir, destination)
        for name in ("vault.enc.bak", "lockout_lab.enc", "lockout_lab.enc.bak"):
            _migrate_optional_file(source_dir, destination, name)
    except MigrationError:
        return SETTINGS_FAILED
    return 0
