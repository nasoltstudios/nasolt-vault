"""Data-location regressions using only disposable encrypted vaults."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nasolt_vault import paths, vault

MASTER = "synthetic-path-fixture-master"


class PackagePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nasolt_package_paths_")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(paths._cache.clear)

    def _encrypted_fixture(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(vault, "VAULT_DIR", str(folder)), \
             mock.patch.object(vault, "VAULT_FILE", str(folder / "vault.enc")):
            session = vault.VaultSession()
            try:
                session.create(MASTER)
                session.save([vault._default_entry(title="Synthetic account",
                                                   password="synthetic-only")], [])
            finally:
                session.close()

    def _open_fixture(self, folder: Path) -> None:
        with mock.patch.object(vault, "VAULT_DIR", str(folder)), \
             mock.patch.object(vault, "VAULT_FILE", str(folder / "vault.enc")):
            session = vault.VaultSession()
            try:
                entries, _ = session.open(MASTER)
                self.assertEqual(entries[0]["title"], "Synthetic account")
            finally:
                session.close()

    def test_source_checkout_uses_legacy_root_data_without_creating_second_vault(self):
        root = Path(self.temp.name) / "source-checkout"
        legacy = root / "data"
        self._encrypted_fixture(legacy)
        with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": "", "APPDATA": str(root / "roaming")}), \
             mock.patch.object(paths, "APP_DIR", str(root)), \
             mock.patch.object(paths, "SOURCE_CHECKOUT", True), \
             mock.patch.object(paths, "FROZEN", False):
            paths._cache.clear()
            self.assertEqual(Path(paths.data_dir()), legacy)
            self._open_fixture(Path(paths.data_dir()))
        self.assertFalse((root / "roaming" / "Nasolt Vault" / "data" / "vault.enc").exists())

    def test_installed_layout_prefers_existing_adjacent_vault_then_appdata(self):
        root = Path(self.temp.name) / "installed"
        root.mkdir()
        (root / "installed.flag").write_text("synthetic marker", encoding="utf-8")
        adjacent = root / "data"
        self._encrypted_fixture(adjacent)
        roaming = Path(self.temp.name) / "roaming"
        with mock.patch.dict(os.environ, {"NASOLT_DATA_DIR": "", "APPDATA": str(roaming)}), \
             mock.patch.object(paths, "APP_DIR", str(root)), \
             mock.patch.object(paths, "SOURCE_CHECKOUT", False), \
             mock.patch.object(paths, "FROZEN", True):
            paths._cache.clear()
            self.assertEqual(Path(paths.data_dir()), adjacent)
            self._open_fixture(Path(paths.data_dir()))
            (adjacent / "vault.enc").unlink()
            paths._cache.clear()
            self.assertEqual(Path(paths.data_dir()), roaming / "Nasolt Vault" / "data")


if __name__ == "__main__":
    unittest.main()
