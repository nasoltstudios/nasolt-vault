"""Synthetic enrollment checks; native consent outcomes are mocked here."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import hello_enrollment
import vault
import windows_hello


class HelloEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_hello_", dir=Path(__file__).parent)
        self.env = mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": self.temp.name})
        self.env.start()
        self.paths = mock.patch.multiple(vault, VAULT_DIR=self.temp.name,
                                         VAULT_FILE=str(Path(self.temp.name) / "vault.enc"))
        self.paths.start()
        self.session = vault.VaultSession()
        self.session.create("Synthetic-only-master-42!")

    def tearDown(self):
        self.session.close()
        self.paths.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_enrollment_is_authenticated_and_removable(self):
        self.assertIsNone(hello_enrollment.read(self.session))
        hello_enrollment.write(self.session, prefer=False)
        self.assertEqual(hello_enrollment.read(self.session), {"prefer": False})
        hello_enrollment.write(self.session, prefer=True)
        self.assertEqual(hello_enrollment.read(self.session), {"prefer": True})
        path = Path(self.temp.name) / "hello-enrollment.json"
        content = path.read_text(encoding="utf-8")
        self.assertNotIn("Synthetic-only-master-42!", content)
        self.assertNotIn('"key"', content)
        obj = json.loads(content)
        obj["prefer"] = False
        path.write_text(json.dumps(obj), encoding="utf-8")
        self.assertIsNone(hello_enrollment.read(self.session))
        path.write_bytes(b"{" + b"x" * 5000)
        self.assertIsNone(hello_enrollment.read(self.session))
        hello_enrollment.remove()
        self.assertFalse(path.exists())

    def test_locked_or_changed_vault_cannot_use_enrollment(self):
        hello_enrollment.write(self.session, prefer=True)
        path = Path(self.temp.name) / "vault.enc"
        original = path.read_bytes()
        path.write_bytes(original + b"tamper")
        self.assertIsNone(hello_enrollment.read(self.session))
        with self.assertRaises(RuntimeError):
            hello_enrollment.write(self.session, prefer=False)
        path.write_bytes(original)
        self.session.close()
        self.assertIsNone(hello_enrollment.read(self.session))

    def test_sidecar_preserves_vault_and_encrypted_backup(self):
        entry = vault._default_entry(title="Fictional account", password="Synthetic-only-secret")
        self.session.save([entry], [])
        primary = Path(self.temp.name, "vault.enc").read_bytes()
        backup = Path(self.temp.name, "vault.enc.bak").read_bytes()
        hello_enrollment.write(self.session, prefer=True)
        self.assertEqual(Path(self.temp.name, "vault.enc").read_bytes(), primary)
        self.assertEqual(Path(self.temp.name, "vault.enc.bak").read_bytes(), backup)
        self.session.close()
        reopened = vault.VaultSession()
        try:
            entries, _groups = reopened.open("Synthetic-only-master-42!")
            self.assertEqual(entries[0]["title"], "Fictional account")
            self.assertEqual(hello_enrollment.read(reopened), {"prefer": True})
        finally:
            reopened.close()

    def test_native_unavailable_paths_are_fail_closed(self):
        with mock.patch.object(windows_hello.sys, "platform", "linux"):
            self.assertNotEqual(windows_hello.availability(), "available")
            self.assertNotEqual(windows_hello.verify(123), "verified")

    @unittest.skipUnless(os.name == "nt", "Windows Hello native API check")
    def test_native_failure_log_does_not_include_exception_value(self):
        if windows_hello.sys.getwindowsversion().build < 22000:
            self.skipTest("Windows Hello integration requires Windows build 22000 or later")
        with mock.patch.object(windows_hello, "_Runtime", side_effect=ValueError("synthetic-secret")), \
             mock.patch.object(windows_hello.logging, "getLogger") as logger:
            self.assertEqual(windows_hello.availability(), "unavailable")
            self.assertEqual(windows_hello.verify(123), "unavailable")
        self.assertNotIn("synthetic-secret", str(logger.mock_calls))


if __name__ == "__main__":
    unittest.main()
