"""Authenticated, nonsecret enrollment preference for unlocked-session Hello.

No vault key or password is persisted. The master password remains required to
open a fully locked vault, and an unreadable/tampered sidecar fails closed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile

from paths import data_dir


def _path() -> str:
    return os.path.join(data_dir(), "hello-enrollment.json")


def _payload(prefer: bool) -> bytes:
    return json.dumps({"version": 1, "prefer": prefer},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def read(session) -> dict | None:
    if not session.matches_disk():
        return None
    try:
        with open(_path(), "rb") as file:
            raw = file.read(4097)
        if len(raw) > 4096:
            return None
        obj = json.loads(raw)
        prefer, tag = obj["prefer"], obj["tag"]
        if obj["version"] != 1 or type(prefer) is not bool or type(tag) is not str:
            return None
        expected = hmac.new(session.hello_enrollment_key(), _payload(prefer), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, tag):
            return {"prefer": prefer}
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, RuntimeError):
        pass
    return None


def write(session, *, prefer: bool) -> None:
    if type(prefer) is not bool or not session.matches_disk():
        raise RuntimeError("Vault session changed; enrollment was not saved")
    tag = hmac.new(session.hello_enrollment_key(), _payload(prefer), hashlib.sha256).hexdigest()
    blob = json.dumps({"version": 1, "prefer": prefer, "tag": tag},
                      sort_keys=True, indent=2).encode("utf-8")
    folder = data_dir()
    fd, temporary = tempfile.mkstemp(prefix=".hello-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(blob)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, _path())
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def remove() -> None:
    try:
        os.unlink(_path())
    except FileNotFoundError:
        pass
