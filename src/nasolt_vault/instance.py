"""Single-instance file lock and one-way, nonsecret activation requests."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from .paths import data_dir

ROUTES = {"normal", "open"}
REQUEST_NAME = re.compile(r"request-[0-9a-f]{32}\.json\Z")


class InstanceCoordinator:
    def __init__(self, folder=None):
        self.folder = Path(folder or data_dir())
        self.lock_file = self.folder / "app.instance.lock"
        self.requests = self.folder / "activation_requests"
        self._file = None

    def acquire(self) -> bool:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_file, "a+b")
        if os.name == "nt":
            import msvcrt
            self._file.seek(0)
            try:
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self._file.close()
                self._file = None
                return False
        else:
            import fcntl
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._file.close()
                self._file = None
                return False
        return True

    def send(self, route: str) -> None:
        if route not in ROUTES:
            raise ValueError("Unknown activation route")
        self.requests.mkdir(parents=True, exist_ok=True)
        name = self.requests / f"request-{uuid.uuid4().hex}.json"
        fd, temp_path = tempfile.mkstemp(prefix=".activation-", dir=self.requests)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump({"route": route, "created": time.time()}, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, name)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def drain_requests(self) -> list[str]:
        if not self.requests.is_dir():
            return []
        routes = []
        for path in self.requests.iterdir():
            if not REQUEST_NAME.fullmatch(path.name):
                continue
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 256:
                    continue
                with path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                age = time.time() - data["created"]
                if data.get("route") in ROUTES and isinstance(age, (int, float)) and -5 <= age <= 30:
                    routes.append(data["route"])
            except (OSError, ValueError, KeyError, TypeError):
                pass
            finally:
                try:
                    path.unlink()
                except OSError:
                    pass
        return routes

    def close(self):
        if self._file is None:
            return
        if os.name == "nt":
            import msvcrt
            self._file.seek(0)
            try:
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        self._file.close()
        self._file = None
