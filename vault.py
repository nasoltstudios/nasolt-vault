"""
vault.py — encrypted storage of entries and groups.

Encrypted payload (inside data/vault.enc):  {"entries": [...], "groups": [...]}
Older vaults stored a bare list of entries; they are upgraded transparently in
memory and written back in the new format on the next save. No migration step.

VaultSession keeps the derived key in memory while the vault is unlocked, so a
save only needs a fresh AES-GCM nonce instead of re-running Argon2id (~0.5 s of
frozen UI on every add / edit / delete in the old version).
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from crypto import (
    SALT_SIZE,
    build_vault_blob,
    decrypt_aes_gcm,
    derive_key,
    encrypt_aes_gcm,
    read_vault_header,
)
from paths import data_dir

VAULT_DIR: str = data_dir()
VAULT_FILE: str = os.path.join(VAULT_DIR, "vault.enc")

UNGROUPED = None  # entries with group_id None belong to the virtual "Ungrouped" bucket

# (key, label) — order is the order shown in the sort dropdown
SORT_OPTIONS: List[Tuple[str, str]] = [
    ("title", "Title A – Z"),
    ("title_desc", "Title Z – A"),
    ("modified", "Recently modified"),
    ("created", "Recently added"),
    ("username", "Username A – Z"),
]


# ---------------------------------------------------------------- helpers
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _default_entry(**overrides: Any) -> Dict[str, Any]:
    now = _now_iso()
    base: Dict[str, Any] = {
        "id": _new_id(), "title": "", "username": "", "password": "", "url": "",
        "notes": "", "group_id": UNGROUPED, "created": now, "modified": now,
    }
    base.update(overrides)
    return base


def _default_group(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {"id": _new_id(), "name": "", "created": _now_iso()}
    base.update(overrides)
    return base


def ensure_vault_dir() -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)


def vault_exists() -> bool:
    return os.path.isfile(VAULT_FILE)


def _unwrap_payload(raw_json: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if isinstance(raw_json, list):
        entries, groups = raw_json, []  # supported legacy payload
    elif isinstance(raw_json, dict) and "entries" in raw_json and "groups" in raw_json:
        entries, groups = raw_json["entries"], raw_json["groups"]
    else:
        raise VaultFormatError("Vault payload has an unsupported structure; no changes were saved.")
    if not isinstance(entries, list) or not isinstance(groups, list):
        raise VaultFormatError("Vault entries or groups are malformed; no changes were saved.")
    entry_ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) for k in ("id", "title", "password")):
            raise VaultFormatError("A vault entry is malformed; no changes were saved.")
        if not entry["id"] or entry["id"] in entry_ids:
            raise VaultFormatError("Vault entry identifiers are invalid; no changes were saved.")
        entry_ids.add(entry["id"])
        if any(k in entry and not isinstance(entry[k], str) for k in ("username", "url", "notes", "created", "modified")):
            raise VaultFormatError("A vault entry field is malformed; no changes were saved.")
        if "group_id" in entry and entry["group_id"] is not None and not isinstance(entry["group_id"], str):
            raise VaultFormatError("A vault entry group is malformed; no changes were saved.")
    group_ids = set()
    for group in groups:
        if not isinstance(group, dict) or any(not isinstance(group.get(k), str) for k in ("id", "name")):
            raise VaultFormatError("A vault group is malformed; no changes were saved.")
        if not group["id"] or group["id"] in group_ids:
            raise VaultFormatError("Vault group identifiers are invalid; no changes were saved.")
        group_ids.add(group["id"])
        if "created" in group and not isinstance(group["created"], str):
            raise VaultFormatError("A vault group date is malformed; no changes were saved.")
    return entries, groups


def _seal(key: bytes, salt: bytes, entries: List[Dict[str, Any]], groups: List[Dict[str, Any]]) -> bytes:
    _unwrap_payload({"entries": entries, "groups": groups})
    plaintext = json.dumps({"entries": entries, "groups": groups}, indent=2).encode("utf-8")
    nonce, tag, ciphertext = encrypt_aes_gcm(plaintext, key)
    return build_vault_blob(salt, nonce, tag, ciphertext)


class VaultFormatError(ValueError):
    """Authenticated vault content or its envelope is structurally invalid."""


class VaultAuthenticationError(ValueError):
    """Password does not authenticate this vault, or ciphertext was damaged."""


class VaultBusyError(RuntimeError):
    """Another process has the vault open for writing."""


class VaultConflictError(RuntimeError):
    """The primary changed since this session opened it."""


class VaultOperationCancelled(RuntimeError):
    """An unlock was revoked before it could establish an open session."""


class _FileLock:
    """OS-owned advisory lock. The file is never unlinked or treated as a PID marker."""

    def __init__(self, path: str):
        self.path = path
        self.file = None

    def acquire(self) -> None:
        ensure_vault_dir()
        self.file = open(self.path, "a+b")
        try:
            self.file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise VaultBusyError("Vault is already open in another app instance. Close it there before trying again.") from exc

    def release(self) -> None:
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None


def _digest(raw: bytes) -> bytes:
    return hashlib.sha256(raw).digest()


def _unique_json_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VaultFormatError("Vault JSON contains duplicate fields; no changes were saved.")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise VaultFormatError("Vault JSON contains an unsupported number; no changes were saved.")


def _read_valid(raw: bytes, master_password: str) -> tuple:
    try:
        header = read_vault_header(raw)
    except ValueError as exc:
        raise VaultFormatError("Vault file header is damaged or unsupported.") from exc
    key = derive_key(master_password, header["salt"])
    try:
        plaintext = decrypt_aes_gcm(header["nonce"], header["tag"], header["ciphertext"], key)
    except ValueError as exc:
        raise VaultAuthenticationError("Password does not unlock this file, or its ciphertext is damaged.") from exc
    try:
        parsed = json.loads(plaintext.decode("utf-8"), object_pairs_hook=_unique_json_object,
                            parse_constant=_reject_json_constant)
        entries, groups = _unwrap_payload(parsed)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VaultFormatError("Vault payload is damaged; no changes were saved.") from None
    return entries, groups, key, header["salt"]


def _write_temp(raw: bytes) -> str:
    fd, path = tempfile.mkstemp(prefix=".vault-", suffix=".tmp", dir=VAULT_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        with open(path, "rb") as verify_file:
            if _digest(verify_file.read()) != _digest(raw):
                raise OSError("Could not verify the staged encrypted vault file.")
        return path
    except BaseException:
        os.unlink(path)
        raise


def _atomic_replace(raw: bytes, path: str) -> None:
    temp_path = _write_temp(raw)
    try:
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _preserve_unique(raw: bytes, label: str) -> str:
    """Keep exact encrypted bytes under a collision-resistant, exclusive name."""
    for _ in range(10):
        path = VAULT_FILE + f".{label}-{uuid.uuid4().hex}"
        try:
            with open(path, "xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            with open(path, "rb") as verify_file:
                if _digest(verify_file.read()) != _digest(raw):
                    raise OSError("Could not verify the preserved encrypted vault copy.")
            return path
        except FileExistsError:
            continue
        except BaseException:
            if os.path.exists(path):
                os.unlink(path)
            raise
    raise OSError("Could not reserve a unique encrypted vault copy.")


def backup_is_valid(master_password: str) -> bool:
    """Only report whether the backup authenticates and has a supported payload."""
    try:
        with open(VAULT_FILE + ".bak", "rb") as f:
            _read_valid(f.read(), master_password)
        return True
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- session
def _serialized_session(method):
    """Keep a lock or save from overlapping a background unlock."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return guarded


def _serialized_opening(method):
    """Reject a queued create or recovery that a lock has already revoked."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        ticket = self._open_ticket()
        with self._state_lock:
            self._check_open_ticket(ticket)
            return method(self, *args, **kwargs)
    return guarded


class VaultSession:
    """An unlocked vault: holds the derived key so saves are instant."""

    def __init__(self) -> None:
        self._state_lock = threading.RLock()
        self._revocation_lock = threading.Lock()
        self._generation = 0
        self._pending_closes = 0
        self._key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._fingerprint: Optional[bytes] = None
        self._lock: Optional[_FileLock] = None

    def _acquire(self) -> None:
        if self._lock is not None:
            raise RuntimeError("This vault session is already open.")
        lock = _FileLock(VAULT_FILE + ".lock")
        lock.acquire()
        self._lock = lock

    def _open_ticket(self) -> int:
        with self._revocation_lock:
            if self._pending_closes:
                raise VaultOperationCancelled("Vault unlock was canceled by a lock request.")
            return self._generation

    def _check_open_ticket(self, ticket: int) -> None:
        with self._revocation_lock:
            if self._pending_closes or ticket != self._generation:
                raise VaultOperationCancelled("Vault unlock was canceled by a lock request.")

    def _close_locked(self) -> None:
        self._key = None
        self._salt = None
        self._fingerprint = None
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    @property
    @_serialized_session
    def is_open(self) -> bool:
        return self._key is not None

    @_serialized_session
    def verify_master_password(self, candidate: str) -> bool:
        """Reauthenticate the current session without opening a second vault session."""
        key, salt, fingerprint = self._key, self._salt, self._fingerprint
        if key is None or salt is None or fingerprint is None:
            return False
        try:
            with open(VAULT_FILE, "rb") as file:
                if not hmac.compare_digest(_digest(file.read()), fingerprint):
                    return False
        except OSError:
            return False
        derived = derive_key(candidate, salt)
        return (self.is_open and self._key is key and self._fingerprint == fingerprint
                and hmac.compare_digest(derived, key))

    @_serialized_session
    def lockout_lab_key(self) -> bytes:
        """Derive a separate key while the authenticated vault session is unlocked."""
        if not self.is_open:
            raise RuntimeError("Vault is locked")
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(algorithm=hashes.SHA256(), length=32, salt=self._salt,
                    info=b"Nasolt Vault Lockout Lab sidecar v1").derive(self._key)

    @_serialized_session
    def hello_enrollment_key(self) -> bytes:
        """Separate integrity key for optional, nonsecret Hello enrollment metadata."""
        if not self.is_open:
            raise RuntimeError("Vault is locked")
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(algorithm=hashes.SHA256(), length=32, salt=self._salt,
                    info=b"Nasolt Vault Hello enrollment v1").derive(self._key)

    @_serialized_session
    def matches_disk(self) -> bool:
        """Reject reauth if the encrypted vault changed since this session opened."""
        if not self.is_open or self._fingerprint is None:
            return False
        try:
            with open(VAULT_FILE, "rb") as file:
                return hmac.compare_digest(_digest(file.read()), self._fingerprint)
        except OSError:
            return False

    def open(self, master_password: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Decrypt the vault. Raises ValueError on a wrong password / corrupt file."""
        ticket = self._open_ticket()
        with self._state_lock:
            self._check_open_ticket(ticket)
            self._acquire()
            try:
                with open(VAULT_FILE, "rb") as f:
                    raw = f.read()
                entries, groups, key, salt = _read_valid(raw, master_password)
                self._check_open_ticket(ticket)
                self._key, self._salt, self._fingerprint = key, salt, _digest(raw)
                return entries, groups
            except BaseException:
                self._close_locked()
                raise

    @_serialized_opening
    def create(self, master_password: str, *, replace_existing: bool = True) -> None:
        """Create an empty vault, preserving any previous encrypted primary first."""
        self._acquire()
        try:
            if vault_exists() and not replace_existing:
                raise FileExistsError("Vault already exists; no replacement was made.")
            old = None
            if vault_exists():
                with open(VAULT_FILE, "rb") as f:
                    old = f.read()
                _preserve_unique(old, "replaced")
                with open(VAULT_FILE, "rb") as f:
                    if _digest(f.read()) != _digest(old):
                        raise VaultConflictError("Vault changed during creation; no replacement was made.")
            salt = os.urandom(SALT_SIZE)
            key = derive_key(master_password, salt)
            blob = _seal(key, salt, [], [])
            _atomic_replace(blob, VAULT_FILE)
            self._key, self._salt, self._fingerprint = key, salt, _digest(blob)
        except BaseException:
            self._close_locked()
            raise

    @_serialized_session
    def save(self, entries: List[Dict[str, Any]], groups: List[Dict[str, Any]]) -> None:
        if not self.is_open:
            raise RuntimeError("Vault is locked")
        blob = _seal(self._key, self._salt, entries, groups)
        try:
            with open(VAULT_FILE, "rb") as f:
                previous = f.read()
        except OSError as exc:
            raise VaultConflictError("Vault file is missing or unreadable; no changes were saved.") from exc
        if _digest(previous) != self._fingerprint:
            raise VaultConflictError("Vault changed outside this session; no changes were saved.")
        # The baseline bytes were authenticated when this session opened or last saved.
        # Finish and flush the new primary before touching the backup.
        temp_path = _write_temp(blob)
        try:
            backup_temp = _write_temp(previous)
            try:
                os.replace(backup_temp, VAULT_FILE + ".bak")
            finally:
                if os.path.exists(backup_temp):
                    os.unlink(backup_temp)
            with open(VAULT_FILE, "rb") as f:
                if _digest(f.read()) != self._fingerprint:
                    raise VaultConflictError("Vault changed during save; no changes were saved.")
            os.replace(temp_path, VAULT_FILE)
            self._fingerprint = _digest(blob)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @_serialized_opening
    def recover_from_backup(self, master_password: str, *, confirmed: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Explicit recovery only; preserve the old primary before replacing it."""
        if not confirmed:
            raise PermissionError("Backup recovery requires explicit confirmation.")
        self._acquire()
        try:
            with open(VAULT_FILE + ".bak", "rb") as f:
                backup = f.read()
            entries, groups, key, salt = _read_valid(backup, master_password)
            old = None
            if vault_exists():
                with open(VAULT_FILE, "rb") as f:
                    old = f.read()
                try:
                    _read_valid(old, master_password)
                except ValueError:
                    pass
                else:
                    raise VaultConflictError("Primary vault already unlocks; recovery was not performed.")
                _preserve_unique(old, "pre-recovery")
                with open(VAULT_FILE, "rb") as f:
                    if _digest(f.read()) != _digest(old):
                        raise VaultConflictError("Primary changed during recovery; no replacement was made.")
            _atomic_replace(backup, VAULT_FILE)
            self._key, self._salt, self._fingerprint = key, salt, _digest(backup)
            return entries, groups
        except BaseException:
            self._close_locked()
            raise

    def close(self) -> None:
        # Revoke at invocation, before waiting for a worker holding _state_lock.
        with self._revocation_lock:
            self._generation += 1
            self._pending_closes += 1
        try:
            with self._state_lock:
                self._close_locked()
        finally:
            with self._revocation_lock:
                self._pending_closes -= 1

    def __del__(self) -> None:
        if getattr(self, "_lock", None) is not None:
            self.close()


# ---------------------------------------------------- functional API (kept)
def create_vault(master_password: str) -> None:
    if vault_exists():
        raise FileExistsError("Vault already exists. Use unlock_vault() instead.")
    ensure_vault_dir()
    VaultSession().create(master_password, replace_existing=False)


def unlock_vault_full(master_password: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return VaultSession().open(master_password)


def unlock_vault(master_password: str) -> List[Dict[str, Any]]:
    return unlock_vault_full(master_password)[0]


def save_vault(master_password: str, entries: List[Dict[str, Any]],
               groups: List[Dict[str, Any]] | None = None) -> None:
    session = VaultSession()
    try:
        existing_entries, existing_groups = session.open(master_password)
        session.save(entries, existing_groups if groups is None else groups)
    finally:
        session.close()


# ---------------------------------------------------------------- entries
def add_entry(entries: List[Dict[str, Any]], **fields: Any) -> List[Dict[str, Any]]:
    entries.append(_default_entry(**fields))
    return entries


def update_entry(entries: List[Dict[str, Any]], entry_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    for e in entries:
        if e["id"] == entry_id:
            e.update(fields)
            e["modified"] = _now_iso()
            return e
    return None


def delete_entry(entries: List[Dict[str, Any]], entry_id: str) -> bool:
    for i, e in enumerate(entries):
        if e["id"] == entry_id:
            entries.pop(i)
            return True
    return False


def search_entries(entries: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Case-insensitive substring search across title, username, url, notes."""
    if not query.strip():
        return list(entries)
    q = query.strip().lower()
    return [e for e in entries if any(q in (e.get(k) or "").lower() for k in ("title", "username", "url", "notes"))]


def get_entry_by_id(entries: List[Dict[str, Any]], entry_id: str) -> Optional[Dict[str, Any]]:
    return next((e for e in entries if e["id"] == entry_id), None)


def sort_entries(entries: List[Dict[str, Any]], sort_by: str = "title", reverse: bool = False) -> List[Dict[str, Any]]:
    """
    Return a new sorted list. sort_by: title | title_desc | username | modified | created.
    modified / created are "most recent first" (fixes the old version, which listed oldest first).
    """
    text = lambda k: (lambda e: ((e.get(k) or "").lower(), (e.get("title") or "").lower()))
    if sort_by == "title_desc":
        return sorted(entries, key=text("title"), reverse=True)
    if sort_by == "username":
        return sorted(entries, key=text("username"), reverse=reverse)
    if sort_by in ("modified", "created"):
        return sorted(entries, key=lambda e: e.get(sort_by) or "", reverse=not reverse)
    return sorted(entries, key=text("title"), reverse=reverse)


# ----------------------------------------------------------------- groups
def add_group(groups: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    group = _default_group(name=name.strip())
    groups.append(group)
    return group


def rename_group(groups: List[Dict[str, Any]], group_id: str, new_name: str) -> Optional[Dict[str, Any]]:
    for g in groups:
        if g["id"] == group_id:
            g["name"] = new_name.strip()
            return g
    return None


def delete_group(groups: List[Dict[str, Any]], entries: List[Dict[str, Any]], group_id: str) -> bool:
    """Remove the group; its entries become Ungrouped (they are NOT deleted)."""
    for i, g in enumerate(groups):
        if g["id"] == group_id:
            groups.pop(i)
            for e in entries:
                if e.get("group_id") == group_id:
                    e["group_id"] = UNGROUPED
            return True
    return False


def get_group_by_id(groups: List[Dict[str, Any]], group_id: str) -> Optional[Dict[str, Any]]:
    return next((g for g in groups if g["id"] == group_id), None)
