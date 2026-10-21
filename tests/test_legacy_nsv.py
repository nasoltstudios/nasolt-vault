"""Fictional NSXP v1 exports built from the recovered legacy format."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nasolt_vault import export, vault  # noqa: E402

PASSWORD = "fictional-export-password-42"
ENTRY_SECRET = "fictional-entry-value-☂"


def legacy_blob(payload: dict, password: str = PASSWORD) -> bytes:
    """Mirror legacy_source/export.py's NSXP writer, without disk plaintext."""
    salt, nonce = os.urandom(32), os.urandom(12)
    key = hash_secret_raw(password.encode("utf-8"), salt, time_cost=3,
                          memory_cost=65536, parallelism=4, hash_len=32, type=Type.ID)
    sealed = AESGCM(key).encrypt(nonce, json.dumps(payload, ensure_ascii=False).encode("utf-8"), None)
    return b"NSXP\x01" + salt + nonce + sealed[-16:] + sealed[:-16]


def fictional_payload() -> dict:
    return {"format": "nasolt-vault-export", "version": 3,
            "groups": ["Récovery ☂", "Empty group"], "entries": [
                {"title": "Mañana ☂", "username": "rémi@example.test", "password": ENTRY_SECRET,
                 "url": "https://example.test/entrée", "notes": "  Fictional line\n☂  ",
                 "group": "Récovery ☂", "created": "2024-01-02T03:04:05",
                 "modified": "2025-06-07T08:09:10"},
                {"title": "Second", "username": "other", "password": "synthetic-two",
                 "url": "", "notes": "", "group": ""}]}


class LegacyNsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_nsv_", dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "fictional.nsv")
        self.path.write_bytes(legacy_blob(fictional_payload()))

    def test_authentic_layout_import_preserves_fields_and_merges_safely(self):
        original = self.path.read_bytes()
        self.assertEqual(original[:5], b"NSXP\x01")
        self.assertEqual(export.LEGACY_HEADER_SIZE, 65)
        self.assertNotIn(ENTRY_SECRET.encode("utf-8"), original)
        rows = export.read_import_file(str(self.path), PASSWORD)
        self.assertEqual(rows[0], fictional_payload()["entries"][0])
        entries = [vault._default_entry(title="Existing", password="keep-me")]
        groups = [{"id": "existing", "name": "Other"}]
        result = export.merge_import(entries, groups, rows)
        self.assertEqual((result.added, result.groups_created), (2, 2))
        self.assertEqual(entries[0]["password"], "keep-me")
        self.assertEqual(entries[1]["group_id"], groups[1]["id"])
        self.assertEqual(entries[1]["notes"], "  Fictional line\n☂  ")
        self.assertEqual(groups[2]["name"], "Empty group")
        self.assertEqual((entries[1]["created"], entries[1]["modified"]),
                         ("2024-01-02T03:04:05", "2025-06-07T08:09:10"))
        self.assertEqual(export.merge_import(entries, groups, rows).skipped, 2)
        self.assertEqual(self.path.read_bytes(), original)

    def test_wrong_or_missing_password_never_changes_destination(self):
        entries = [vault._default_entry(title="Existing", password="keep-me")]
        groups = [{"id": "existing", "name": "Other"}]
        before = ([e.copy() for e in entries], [g.copy() for g in groups])
        for password in (None, "wrong-fictional-password"):
            with self.subTest(password_is_missing=password is None):
                with self.assertRaises(ValueError) as error:
                    rows = export.read_import_file(str(self.path), password)
                    export.merge_import(entries, groups, rows)
                self.assertNotIn(ENTRY_SECRET, str(error.exception))
                self.assertEqual((entries, groups), before)

    def test_empty_groups_only_survive_vault_restart(self):
        payload = fictional_payload() | {"entries": [], "groups": ["Unused recovery route"]}
        self.path.write_bytes(legacy_blob(payload))
        rows = export.read_import_file(str(self.path), PASSWORD)
        self.assertEqual(len(rows), 0)
        vault_path = str(Path(self.temp.name, "vault.enc"))
        with mock.patch.object(vault, "VAULT_DIR", self.temp.name), \
             mock.patch.object(vault, "VAULT_FILE", vault_path):
            session = vault.VaultSession()
            try:
                session.create("fictional-master-only-42")
                entries = [vault._default_entry(title="Existing", password="keep-me")]
                groups = [{"id": "existing", "name": "Other"}]
                session.save(entries, groups)
                result = export.merge_import(entries, groups, rows)
                self.assertEqual((result.added, result.groups_created), (0, 1))
                session.save(entries, groups)
            finally:
                session.close()
            reopened = vault.VaultSession()
            try:
                saved_entries, saved_groups = reopened.open("fictional-master-only-42")
                self.assertEqual(saved_entries[0]["password"], "keep-me")
                self.assertEqual({g["name"] for g in saved_groups},
                                 {"Other", "Unused recovery route"})
            finally:
                reopened.close()

    def test_failed_parse_does_not_change_existing_vault_bytes(self):
        vault_path = str(Path(self.temp.name, "vault.enc"))
        with mock.patch.object(vault, "VAULT_DIR", self.temp.name), \
             mock.patch.object(vault, "VAULT_FILE", vault_path):
            session = vault.VaultSession()
            try:
                session.create("fictional-master-only-42")
                entries = [vault._default_entry(title="Existing", password="keep-me")]
                groups = [{"id": "existing", "name": "Other"}]
                session.save(entries, groups)
                before = Path(vault_path).read_bytes()
                for damaged in (False, True):
                    with self.subTest(damaged=damaged):
                        if damaged:
                            blob = self.path.read_bytes()
                            self.path.write_bytes(blob[:49] + bytes([blob[49] ^ 1]) + blob[50:])
                        with self.assertRaises(ValueError):
                            export.read_import_file(str(self.path), "wrong" if not damaged else PASSWORD)
                        self.assertEqual(Path(vault_path).read_bytes(), before)
                        self.assertEqual(entries[0]["password"], "keep-me")
                        self.assertEqual(groups[0]["name"], "Other")
            finally:
                session.close()

    def test_bad_header_version_tag_ciphertext_and_truncation(self):
        original = self.path.read_bytes()
        for label, changed in (("magic", b"XXXX" + original[4:]),
                               ("version", original[:4] + b"\x02" + original[5:]),
                               ("tag", original[:49] + bytes([original[49] ^ 1]) + original[50:]),
                               ("ciphertext", original[:-1] + bytes([original[-1] ^ 1])),
                               ("truncated", original[:40])):
            with self.subTest(label=label):
                path = Path(self.temp.name, label + ".nsv")
                path.write_bytes(changed)
                with self.assertRaises(ValueError):
                    export.read_import_file(str(path), PASSWORD)

    def test_payload_validation_and_oversize(self):
        for label, change in (("wrong-format", {"format": "other"}),
                              ("wrong-version", {"version": 4}),
                              ("bad-groups", {"groups": [3]}),
                              ("bad-entry", {"entries": [{"title": "okay"}, {"title": 3}]}),
                              ("missing-title", {"entries": [{"password": "synthetic"}]})):
            with self.subTest(label=label):
                payload = fictional_payload() | change
                self.path.write_bytes(legacy_blob(payload))
                with self.assertRaises(ValueError):
                    export.read_import_file(str(self.path), PASSWORD)
        with mock.patch.object(export, "MAX_ENCRYPTED_IMPORT_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "too large"):
                export.read_import_file(str(self.path), PASSWORD)


if __name__ == "__main__":
    unittest.main()
