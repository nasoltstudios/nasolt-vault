"""Offline recovery-route model and encrypted sidecar storage.

Only named dependencies and evidence flags enter the model. Passwords and
recovery-code values are neither accepted nor read from vault entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import vault

MAGIC = b"NSLL1"
MAX_FILE = 2 * 1024 * 1024
SCENARIOS = {"lost_phone": ("Lost phone", "phone"),
             "primary_email": ("Inaccessible primary email", "primary_email"),
             "lost_computer": ("Lost computer", "computer")}
KINDS = {"account", "device", "method"}
ROLES = {"none", "phone", "primary_email", "computer"}
EVIDENCE = {"unknown", "documented", "verified"}


class LabError(ValueError):
    """Unsafe, inaccessible, or malformed Lockout Lab metadata."""


def empty_model() -> dict:
    return {"version": 1, "nodes": []}


def validate(model: object) -> dict:
    if (not isinstance(model, dict) or set(model) != {"version", "nodes"} or
            type(model["version"]) is not int or model["version"] != 1):
        raise LabError("Lockout Lab data has an unsupported structure.")
    nodes = model["nodes"]
    if not isinstance(nodes, list) or len(nodes) > 200:
        raise LabError("Lockout Lab has too many or malformed items.")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "name", "kind", "role", "evidence", "routes"}:
            raise LabError("A Lockout Lab item is malformed.")
        ident, name, kind, role, evidence, routes = (node[k] for k in ("id", "name", "kind", "role", "evidence", "routes"))
        if not isinstance(ident, str) or not ident or len(ident) > 64 or ident in ids:
            raise LabError("Lockout Lab item identifiers are invalid.")
        ids.add(ident)
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise LabError("A Lockout Lab item name is invalid.")
        if (not isinstance(kind, str) or kind not in KINDS or
                not isinstance(role, str) or role not in ROLES or
                not isinstance(evidence, str) or evidence not in EVIDENCE):
            raise LabError("A Lockout Lab item type or status is invalid.")
        if not isinstance(routes, list) or len(routes) > 20:
            raise LabError("Recovery routes are malformed.")
        for route in routes:
            if not isinstance(route, list) or not route or len(route) > 20 or any(not isinstance(ref, str) or not ref for ref in route):
                raise LabError("A recovery route is malformed.")
            if len(set(route)) != len(route):
                raise LabError("A recovery route repeats a requirement.")
    return model


def add_node(model: dict, name: str, kind: str, role: str = "none", evidence: str = "unknown") -> str:
    ident = uuid.uuid4().hex
    candidate = {"id": ident, "name": name.strip(), "kind": kind, "role": role,
                 "evidence": evidence, "routes": []}
    validate({"version": 1, "nodes": model["nodes"] + [candidate]})
    model["nodes"].append(candidate)
    return ident


def add_route(model: dict, target: str, requirements: list[str]) -> None:
    validate(model)
    node = next((n for n in model["nodes"] if n["id"] == target), None)
    known = {n["id"] for n in model["nodes"]}
    if node is None or not requirements or len(set(requirements)) != len(requirements) or any(ref not in known for ref in requirements):
        raise LabError("Choose an item and at least one known requirement.")
    node["routes"].append(list(requirements))
    try:
        validate(model)
    except LabError:
        node["routes"].pop()
        raise


def circular_nodes(model: dict) -> set[str]:
    """Return nodes in dependency cycles, including self-dependencies."""
    validate(model)
    graph = {n["id"]: [r for route in n["routes"] for r in route] for n in model["nodes"]}
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for ref in graph[node]:
            if ref not in graph:
                continue
            if ref not in indices:
                visit(ref)
                low[node] = min(low[node], low[ref])
            elif ref in active:
                low[node] = min(low[node], indices[ref])
        if low[node] == indices[node]:
            component = []
            while True:
                ref = stack.pop()
                active.remove(ref)
                component.append(ref)
                if ref == node:
                    break
            if len(component) > 1 or node in graph[node]:
                cycles.update(component)

    for ident in graph:
        if ident not in indices:
            visit(ident)
    return cycles


def simulate(model: dict, scenario: str) -> list[dict]:
    """Return modeled outcomes; available means a modeled route, never a guarantee."""
    validate(model)
    if scenario not in SCENARIOS:
        raise LabError("Unknown scenario.")
    lost_role = SCENARIOS[scenario][1]
    nodes = {n["id"]: n for n in model["nodes"]}
    cycles = circular_nodes(model)
    state = {ident: ("blocked" if n["role"] == lost_role else "unknown") for ident, n in nodes.items()}
    for ident, n in nodes.items():
        if n["role"] != lost_role and not n["routes"] and n["kind"] != "account" and n["evidence"] != "unknown":
            state[ident] = "available"
    # Monotone refinement: unknown nodes can become available or blocked.
    for _ in range(len(nodes) + 1):
        changed = False
        for ident, n in nodes.items():
            if n["role"] == lost_role or not n["routes"] or state[ident] != "unknown":
                continue
            routes = []
            for route in n["routes"]:
                values = [state.get(ref, "unknown") for ref in route]
                routes.append("blocked" if "blocked" in values else
                              "available" if all(v == "available" for v in values) else "unknown")
            new = "available" if "available" in routes else "blocked" if all(v == "blocked" for v in routes) else "unknown"
            if new != state[ident]:
                state[ident] = new
                changed = True
        if not changed:
            break
    result = []
    for ident, n in nodes.items():
        if n["kind"] != "account":
            continue
        missing = sorted({ref for route in n["routes"] for ref in route if ref not in nodes})
        unknown = not n["routes"] or bool(missing) or any(state.get(ref) == "unknown" for route in n["routes"] for ref in route)
        status = state[ident]
        if n["role"] == lost_role:
            reason = "This account is the item unavailable in the selected scenario."
        elif status == "available":
            reason = "At least one documented route has all modeled requirements available."
        elif status == "blocked":
            reason = "Every documented route includes a requirement unavailable in this scenario."
        else:
            reason = "No complete available route can be established from the information entered."
        circular = ident in cycles or any(ref in cycles for route in n["routes"] for ref in route)
        steps = []
        if unknown:
            steps.append("Document the missing recovery requirements and where they are kept.")
        if circular:
            steps.append("Break the circular dependency with an independent recovery method.")
        if status == "blocked":
            steps.append("Add an independent recovery route before this loss happens.")
        if n["evidence"] != "verified":
            steps.append("Test this account's recovery steps and mark them user-verified.")
        result.append({"id": ident, "name": n["name"], "status": status, "reason": reason,
                       "unknown": unknown, "circular": circular,
                       "missing_references": missing, "steps": steps})
    return result


class LabStore:
    """AES-GCM sidecar protected by the current vault session and its lock."""

    def __init__(self, session: vault.VaultSession, path: Path | None = None):
        self.session = session
        self.path = Path(path) if path is not None else Path(vault.VAULT_DIR) / "lockout_lab.enc"
        self._fingerprint: bytes | None = None
        self._loaded = False

    def _key(self) -> bytes:
        return self.session.lockout_lab_key()

    @staticmethod
    def _digest(raw: bytes) -> bytes:
        return hashlib.sha256(raw).digest()

    def _open_blob(self, raw: bytes) -> dict:
        if len(raw) < len(MAGIC) + 12 + 16 or len(raw) > MAX_FILE or not raw.startswith(MAGIC):
            raise LabError("Lockout Lab file is damaged or unsupported; no changes were made.")
        try:
            plain = AESGCM(self._key()).decrypt(raw[len(MAGIC):len(MAGIC)+12], raw[len(MAGIC)+12:], MAGIC)
            model = json.loads(plain.decode("utf-8"), object_pairs_hook=vault._unique_json_object,
                               parse_constant=vault._reject_json_constant)
            return validate(model)
        except (InvalidTag, ValueError, UnicodeError) as exc:
            raise LabError("Lockout Lab cannot be authenticated or parsed; encrypted files were kept.") from exc

    def load(self) -> dict:
        self._key()  # require an unlocked session even when no sidecar exists
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            self._fingerprint = None
            self._loaded = True
            return empty_model()
        model = self._open_blob(raw)
        self._fingerprint = self._digest(raw)
        self._loaded = True
        return model

    def _stage(self, raw: bytes) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".lockout-lab-", suffix=".tmp", dir=self.path.parent)
        staged = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self._digest(staged.read_bytes()) != self._digest(raw):
                raise OSError("Staged Lockout Lab data did not verify.")
            return staged
        except BaseException:
            staged.unlink(missing_ok=True)
            raise

    def save(self, model: dict) -> None:
        if not self._loaded:
            raise LabError("Load Lockout Lab before saving it.")
        validate(model)
        key = self._key()
        try:
            previous = self.path.read_bytes()
        except FileNotFoundError:
            previous = None
        if (None if previous is None else self._digest(previous)) != self._fingerprint:
            raise LabError("Lockout Lab changed outside this session; nothing was saved.")
        plain = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(12)
        raw = MAGIC + nonce + AESGCM(key).encrypt(nonce, plain, MAGIC)
        if len(raw) > MAX_FILE:
            raise LabError("Lockout Lab is too large to save.")
        stage = self._stage(raw)
        try:
            if previous is not None:
                backup = self._stage(previous)
                try:
                    os.replace(backup, Path(str(self.path) + ".bak"))
                finally:
                    backup.unlink(missing_ok=True)
            try:
                current = self.path.read_bytes()
            except FileNotFoundError:
                current = None
            if (None if current is None else self._digest(current)) != self._fingerprint:
                raise LabError("Lockout Lab changed during save; nothing was saved.")
            os.replace(stage, self.path)
            self._fingerprint = self._digest(raw)
        finally:
            stage.unlink(missing_ok=True)

    def recover_from_backup(self, *, confirmed: bool = False) -> dict:
        """Restore only an authenticated backup, preserving a damaged primary."""
        if not confirmed:
            raise PermissionError("Lockout Lab backup recovery requires confirmation.")
        self._key()
        try:
            backup_raw = Path(str(self.path) + ".bak").read_bytes()
        except OSError as exc:
            raise LabError("No readable Lockout Lab backup is available.") from exc
        model = self._open_blob(backup_raw)
        try:
            previous = self.path.read_bytes()
        except FileNotFoundError:
            previous = None
        if previous is not None:
            try:
                self._open_blob(previous)
            except LabError:
                pass
            else:
                raise LabError("The current Lockout Lab file opens; recovery was not performed.")
            preserved = Path(str(self.path) + ".pre-recovery-" + uuid.uuid4().hex)
            with preserved.open("xb") as stream:
                stream.write(previous)
                stream.flush()
                os.fsync(stream.fileno())
            if self._digest(preserved.read_bytes()) != self._digest(previous):
                raise LabError("Could not verify the preserved damaged file; recovery stopped.")
        stage = self._stage(backup_raw)
        try:
            if previous is None and self.path.exists():
                raise LabError("Lockout Lab appeared during recovery; no replacement was made.")
            if previous is not None and self._digest(self.path.read_bytes()) != self._digest(previous):
                raise LabError("Lockout Lab changed during recovery; no replacement was made.")
            os.replace(stage, self.path)
            self._fingerprint = self._digest(backup_raw)
            self._loaded = True
            return model
        finally:
            stage.unlink(missing_ok=True)
