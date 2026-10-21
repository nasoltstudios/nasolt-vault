"""
export.py — export/import encrypted NVE files and legacy plaintext CSV / JSON.

Round-trip guarantee: a file written by export_vault() can be read by
read_import_file() and merged with merge_import() so every entry comes back
with its group. Older exports (no group column, bare JSON list) still import.
NVE is a separate portable export format; it does not change vault.enc.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .crypto import NONCE_SIZE, SALT_SIZE, derive_key

from .paths import default_export_dir

CSV_FIELDNAMES = ["title", "username", "password", "url", "notes", "group", "created", "modified"]
FORMAT_TAG = "nasolt-vault-export"
ENCRYPTED_MAGIC = b"NSLX\x01"
MAX_ENCRYPTED_IMPORT_BYTES = 100 * 1024 * 1024
LEGACY_MAGIC = b"NSXP"
LEGACY_VERSION = 1
LEGACY_SALT_SIZE = 32
LEGACY_NONCE_SIZE = 12
LEGACY_TAG_SIZE = 16
LEGACY_HEADER_SIZE = len(LEGACY_MAGIC) + 1 + LEGACY_SALT_SIZE + LEGACY_NONCE_SIZE + LEGACY_TAG_SIZE

# header aliases so CSVs from other managers import too
_ALIASES = {
    "title": ("title", "name", "site", "account", "label"),
    "username": ("username", "user", "login", "login_username", "email", "user name"),
    "password": ("password", "pass", "login_password", "pwd"),
    "url": ("url", "website", "site url", "login_uri", "web site", "link"),
    "notes": ("notes", "note", "comments", "comment", "extra", "description"),
    "group": ("group", "folder", "category", "grouping"),
    "created": ("created", "date created", "created_at"),
    "modified": ("modified", "date modified", "modified_at", "updated"),
}


# ------------------------------------------------------------------ export
def _group_name_map(groups: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    return {g["id"]: g["name"] for g in (groups or [])}


def _rows(entries: List[Dict[str, Any]], groups: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    names = _group_name_map(groups)
    rows = []
    for e in entries:
        rows.append({
            "title": e.get("title", ""), "username": e.get("username", ""),
            "password": e.get("password", ""), "url": e.get("url", ""),
            "notes": e.get("notes", ""), "group": names.get(e.get("group_id") or "", ""),
            "created": e.get("created", ""), "modified": e.get("modified", ""),
        })
    return rows


def resolve_export_dir(dest_dir: Optional[str]) -> str:
    """An explicit destination must work; never redirect plaintext silently."""
    candidate = dest_dir or default_export_dir()
    try:
        os.makedirs(candidate, exist_ok=True)
        return candidate
    except OSError:
        raise OSError("The chosen export folder is unavailable. Choose another folder in Import / Export.") from None


def export_vault(entries: List[Dict[str, Any]], fmt: str = "JSON", dest_dir: Optional[str] = None,
                 groups: Optional[List[Dict[str, Any]]] = None, password: Optional[str] = None) -> str:
    fmt = fmt.upper()
    if fmt not in ("CSV", "JSON", "NVE"):
        raise ValueError(f"Unsupported export format: {fmt}")
    if fmt == "NVE" and not password:
        raise ValueError("An export password is required for encrypted files.")
    target = resolve_export_dir(dest_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = _rows(entries, groups)
    if fmt in ("JSON", "NVE"):
        payload = {"format": FORMAT_TAG, "version": 2, "exported": datetime.datetime.now().isoformat(timespec="seconds"),
                   "groups": [g["name"] for g in (groups or [])], "entries": rows}
    if fmt == "NVE":
        # Encrypt in memory: no intermediate plaintext file ever reaches disk.
        salt = os.urandom(SALT_SIZE)
        nonce = os.urandom(NONCE_SIZE)
        header = ENCRYPTED_MAGIC + salt + nonce
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encrypted = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, header)
        blob = header + encrypted
    for number in range(10000):
        suffix = "" if number == 0 else f"_{number}"
        path = os.path.join(target, f"nasolt_vault_export_{stamp}{suffix}.{fmt.lower()}")
        try:
            if fmt == "NVE":
                f = open(path, "xb")
            else:
                f = open(path, "x", newline="", encoding="utf-8-sig" if fmt == "CSV" else "utf-8")
        except FileExistsError:
            continue
        except OSError:
            raise OSError("Could not create an export file in the chosen folder.") from None
        try:
            # x is exclusive: a repeated export never truncates an existing one.
            with f:
                if fmt == "NVE":
                    f.write(blob)
                elif fmt == "CSV":
                    w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                    w.writeheader()
                    w.writerows(rows)
                else:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            return os.path.abspath(path)
        except BaseException as exc:
            removed = True
            try:
                os.unlink(path)
            except OSError:
                removed = False
            if not isinstance(exc, Exception):
                raise
            if not removed:
                raise OSError("Export failed; an incomplete file may remain in the chosen folder.") from None
            raise OSError("Export failed; no completed export was kept.") from None
    raise OSError("Could not reserve a unique export filename.")


# ------------------------------------------------------------------ import
def _pick(row: Dict[str, Any], field: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for alias in _ALIASES[field]:
        if alias in lowered and lowered[alias] is not None:
            return str(lowered[alias])
    return ""


def _read_legacy_nsv(blob: bytes, password: str) -> tuple[List[Dict[str, Any]], List[str]]:
    """Read the original NSXP v1 envelope; never use its layout for new exports."""
    if len(blob) < LEGACY_HEADER_SIZE + 1 or blob[:len(LEGACY_MAGIC)] != LEGACY_MAGIC:
        raise ValueError("This is not a supported legacy Nasolt export, or the file is damaged.")
    if blob[len(LEGACY_MAGIC)] != LEGACY_VERSION:
        raise ValueError("This legacy Nasolt export version is not supported.")
    if not password:
        raise ValueError("Enter the password used when this export was created.")
    offset = len(LEGACY_MAGIC) + 1
    salt = blob[offset:offset + LEGACY_SALT_SIZE]
    offset += LEGACY_SALT_SIZE
    nonce = blob[offset:offset + LEGACY_NONCE_SIZE]
    offset += LEGACY_NONCE_SIZE
    tag = blob[offset:offset + LEGACY_TAG_SIZE]
    ciphertext = blob[offset + LEGACY_TAG_SIZE:]
    try:
        # NSXP stores the tag before ciphertext and authenticates no header/AAD.
        key = hash_secret_raw(password.encode("utf-8"), salt, time_cost=3,
                              memory_cost=65536, parallelism=4, hash_len=32, type=Type.ID)
        clear = AESGCM(key).decrypt(nonce, ciphertext + tag, None)
    except (InvalidTag, ValueError):
        raise ValueError("Decryption failed. Check the export password or file integrity.") from None
    try:
        data = json.loads(clear.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("The authenticated legacy export content is damaged.") from None
    if (not isinstance(data, dict) or data.get("format") != FORMAT_TAG
            or type(data.get("version")) is not int or data["version"] != 3):
        raise ValueError("The legacy export contains an unsupported data format.")
    groups, entries = data.get("groups"), data.get("entries")
    if (not isinstance(groups, list) or not all(isinstance(g, str) for g in groups)
            or not isinstance(entries, list)):
        raise ValueError("The legacy export contains invalid groups or entries.")
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("The legacy export contains invalid entries.")
        for field in CSV_FIELDNAMES:
            if field in row and not isinstance(row[field], str):
                raise ValueError("The legacy export contains invalid entry fields.")
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            raise ValueError("The legacy export contains an entry without a title.")
    return entries, groups


class ImportRows(list):
    """Normalised rows with optional names of empty legacy export groups."""

    def __init__(self, rows: List[Dict[str, str]], group_names: List[str]):
        super().__init__(rows)
        self.group_names = group_names


def read_import_file(filepath: str, password: Optional[str] = None) -> List[Dict[str, str]]:
    """Authenticate encrypted exports or parse CSV/JSON into normalised rows."""
    ext = os.path.splitext(filepath)[1].lower()
    legacy_groups: List[str] = []
    try:
        if ext == ".nsv":
            with open(filepath, "rb") as f:
                blob = f.read(MAX_ENCRYPTED_IMPORT_BYTES + 1)
            if len(blob) > MAX_ENCRYPTED_IMPORT_BYTES:
                raise ValueError("The encrypted export is too large to import.")
            raw, legacy_groups = _read_legacy_nsv(blob, password or "")
        elif ext == ".nve":
            if not password:
                raise ValueError("Enter the password used when this export was created.")
            with open(filepath, "rb") as f:
                blob = f.read(MAX_ENCRYPTED_IMPORT_BYTES + 1)
            if len(blob) > MAX_ENCRYPTED_IMPORT_BYTES:
                raise ValueError("The encrypted export is too large to import.")
            header_size = len(ENCRYPTED_MAGIC) + SALT_SIZE + NONCE_SIZE
            if not blob.startswith(ENCRYPTED_MAGIC) or len(blob) < header_size + 17:
                raise ValueError("This is not a supported encrypted Nasolt export, or the file is damaged.")
            salt = blob[len(ENCRYPTED_MAGIC):len(ENCRYPTED_MAGIC) + SALT_SIZE]
            nonce = blob[len(ENCRYPTED_MAGIC) + SALT_SIZE:header_size]
            try:
                clear = AESGCM(derive_key(password, salt)).decrypt(nonce, blob[header_size:], blob[:header_size])
            except (InvalidTag, ValueError):
                raise ValueError("Decryption failed. Check the export password or file integrity.") from None
            try:
                data = json.loads(clear.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError("The authenticated export content is damaged.") from None
            if not isinstance(data, dict) or data.get("format") != FORMAT_TAG or data.get("version") != 2:
                raise ValueError("The encrypted export contains an unsupported data format.")
            data = data.get("entries")
            if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
                raise ValueError("The encrypted export contains invalid entries.")
            raw = data
        elif ext == ".json":
            with open(filepath, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("entries", data.get("items", []))
            if not isinstance(data, list):
                raise ValueError("The JSON file does not contain a list of entries.")
            raw = [r for r in data if isinstance(r, dict)]
        elif ext == ".csv":
            with open(filepath, "r", newline="", encoding="utf-8-sig") as f:
                sample = f.read(4096)
                f.seek(0)
                try:  # Excel in many locales saves ';' or tab separated "CSV"
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                raw = [dict(r) for r in csv.DictReader(f, dialect=dialect)]
        else:
            raise ValueError(f"Unsupported file type '{ext or '(none)'}'. Choose a .nsv, .nve, .csv, or .json file.")
    except UnicodeDecodeError:
        raise ValueError("The file is not valid UTF-8 text.")
    except json.JSONDecodeError as e:
        raise ValueError(f"The JSON file is damaged ({e.msg}).")

    rows: List[Dict[str, str]] = []
    for r in raw:
        row = {f: _pick(r, f) if ext == ".nsv" or f == "password" else _pick(r, f).strip()
               for f in _ALIASES}
        if row["title"].strip():
            rows.append(row)
    if not rows and not (ext == ".nsv" and any(name.strip() for name in legacy_groups)):
        raise ValueError("No usable entries found — every entry needs at least a title.")
    return ImportRows(rows, legacy_groups) if ext == ".nsv" else rows


def import_entries(filepath: str, password: Optional[str] = None) -> List[Dict[str, str]]:  # backwards-compatible name
    return read_import_file(filepath, password=password)


@dataclass
class ImportResult:
    added: int = 0
    skipped: int = 0
    groups_created: int = 0


def _dup_key(title: str, username: str, url: str, password: str) -> tuple:
    return (title.strip().lower(), username.strip().lower(), url.strip().lower(), password)


def merge_import(entries: List[Dict[str, Any]], groups: List[Dict[str, Any]], rows: List[Dict[str, str]]) -> ImportResult:
    """Merge parsed rows into the live lists (mutates them). Exact duplicates are skipped; groups are re-created by name."""
    from .vault import _default_entry, add_group  # local import: vault needs no export

    result = ImportResult()
    seen = {_dup_key(e.get("title", ""), e.get("username", ""), e.get("url", ""), e.get("password", "")) for e in entries}
    by_name = {g["name"].lower(): g for g in groups}

    for row in rows:
        key = _dup_key(row["title"], row["username"], row["url"], row["password"])
        if key in seen:
            result.skipped += 1
            continue
        seen.add(key)

        group_id = None
        gname = row.get("group", "").strip()
        if gname:
            g = by_name.get(gname.lower())
            if g is None:
                g = add_group(groups, gname)
                by_name[gname.lower()] = g
                result.groups_created += 1
            group_id = g["id"]

        fields = {"title": row["title"], "username": row["username"], "password": row["password"],
                  "url": row["url"], "notes": row["notes"], "group_id": group_id}
        for stamp in ("created", "modified"):
            if row.get(stamp):
                fields[stamp] = row[stamp]
        entries.append(_default_entry(**fields))
        result.added += 1
    for name in getattr(rows, "group_names", ()):
        cleaned = name.strip()
        if cleaned and cleaned.lower() not in by_name:
            by_name[cleaned.lower()] = add_group(groups, cleaned)
            result.groups_created += 1
    return result
