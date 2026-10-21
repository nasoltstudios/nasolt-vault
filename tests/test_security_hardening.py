"""Concurrency regressions using only a disposable vault and synthetic text."""

import threading
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_vault_baseline as baseline

from nasolt_vault import clipboard
from nasolt_vault import app_settings
from nasolt_vault import paths


class SessionLifecycleTests(unittest.TestCase):
    setUp = baseline.VaultBaselineTests.setUp

    def test_close_waits_for_background_unlock_then_clears_key(self):
        vault = baseline.vault
        initial = vault.VaultSession()
        initial.create(baseline.MASTER)
        initial.close()
        session = vault.VaultSession()
        self.addCleanup(session.close)
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        errors = []
        original = vault._read_valid

        def delayed(*args):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("synthetic unlock gate timed out")
            return original(*args)

        def unlock():
            try:
                session.open(baseline.MASTER)
            except Exception as exc:
                errors.append(exc)

        def lock():
            try:
                session.close()
            finally:
                closed.set()

        with mock.patch.object(vault, "_read_valid", side_effect=delayed):
            opener = threading.Thread(target=unlock)
            closer = threading.Thread(target=lock)
            opener.start()
            try:
                self.assertTrue(entered.wait(10))
                closer.start()
                self.assertFalse(closed.wait(0.1), "close returned during in-flight unlock")
            finally:
                release.set()
                opener.join(10)
                if closer.ident is not None:
                    closer.join(10)
        self.assertFalse(opener.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual([type(error) for error in errors], [vault.VaultOperationCancelled])
        self.assertTrue(closed.is_set())
        self.assertFalse(session.is_open)
        self.assertIsNone(session._lock)

    def test_lock_revokes_unlock_waiting_for_session_mutex(self):
        vault = baseline.vault
        owner = vault.VaultSession()
        owner.create(baseline.MASTER)
        owner.close()
        session = vault.VaultSession()
        self.addCleanup(session.close)
        entered, release = threading.Event(), threading.Event()
        outcomes = []

        def unlock():
            try:
                session.open(baseline.MASTER)
                outcomes.append("opened")
            except Exception as exc:
                outcomes.append(type(exc))

        with session._state_lock:
            worker = threading.Thread(target=unlock)
            worker.start()
            self.assertTrue(self._wait_for(lambda: worker.is_alive()))
            closer = threading.Thread(target=lambda: (entered.set(), session.close(), release.set()))
            closer.start()
            self.assertTrue(entered.wait(5))
            self.assertTrue(self._wait_for(lambda: session._generation > 0))
            with self.assertRaises(vault.VaultOperationCancelled):
                session.open(baseline.MASTER)
        worker.join(10)
        closer.join(10)
        self.assertFalse(worker.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual(outcomes, [vault.VaultOperationCancelled])
        self.assertFalse(session.is_open)
        self.assertEqual(session.open(baseline.MASTER), ([], []))

    @staticmethod
    def _wait_for(predicate, timeout=5):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False

    def test_two_unlocks_do_not_close_successful_session(self):
        vault = baseline.vault
        seed = vault.VaultSession()
        seed.create(baseline.MASTER)
        seed.close()
        session = vault.VaultSession()
        self.addCleanup(session.close)
        entered, release = threading.Event(), threading.Event()
        outcomes = []
        original = vault._read_valid

        def delayed(*args):
            entered.set()
            self.assertTrue(release.wait(10))
            return original(*args)

        def unlock():
            try:
                session.open(baseline.MASTER)
                outcomes.append("opened")
            except Exception as exc:
                outcomes.append(type(exc))

        with mock.patch.object(vault, "_read_valid", side_effect=delayed):
            first = threading.Thread(target=unlock)
            second = threading.Thread(target=unlock)
            first.start()
            self.assertTrue(entered.wait(10))
            second.start()
            release.set()
            first.join(10)
            second.join(10)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertCountEqual(outcomes, ["opened", RuntimeError])
        self.assertTrue(session.is_open)

    def test_lock_revokes_queued_vault_creation_before_file_write(self):
        vault = baseline.vault
        session = vault.VaultSession()
        self.addCleanup(session.close)
        errors = []
        with session._state_lock:
            creator = threading.Thread(target=lambda: self._capture_error(
                errors, lambda: session.create(baseline.MASTER)))
            creator.start()
            self.assertTrue(self._wait_for(lambda: creator.is_alive()))
            closer = threading.Thread(target=session.close)
            closer.start()
            self.assertTrue(self._wait_for(lambda: session._generation > 0))
        creator.join(10)
        closer.join(10)
        self.assertFalse(creator.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [vault.VaultOperationCancelled])
        self.assertFalse(vault.vault_exists())
        self.assertFalse(session.is_open)

    @staticmethod
    def _capture_error(errors, action):
        try:
            action()
        except Exception as exc:
            errors.append(type(exc))

    def test_reauthentication_and_save_finish_before_close_returns(self):
        vault = baseline.vault
        session = vault.VaultSession()
        session.create(baseline.MASTER)
        self.addCleanup(session.close)
        for name, operation in (("derive_key", lambda: session.verify_master_password(baseline.MASTER)),
                                ("_seal", lambda: session.save([], []))):
            entered, release, closed = threading.Event(), threading.Event(), threading.Event()
            target = getattr(vault, name)

            def delayed(*args):
                entered.set()
                self.assertTrue(release.wait(10))
                return target(*args)

            with mock.patch.object(vault, name, side_effect=delayed):
                worker = threading.Thread(target=operation)
                worker.start()
                self.assertTrue(entered.wait(10))
                closer = threading.Thread(target=lambda: (session.close(), closed.set()))
                closer.start()
                self.assertFalse(closed.wait(0.1))
                release.set()
                worker.join(10)
                closer.join(10)
            self.assertFalse(worker.is_alive())
            self.assertFalse(closer.is_alive())
            self.assertFalse(session.is_open)
            if name == "derive_key":
                session.open(baseline.MASTER)


class ClipboardTimerTests(unittest.TestCase):
    def test_expired_timer_cannot_clear_a_newer_copy(self):
        memory = {"value": ""}
        with mock.patch.object(clipboard.pyperclip, "copy", side_effect=lambda value: memory.__setitem__("value", value)), \
             mock.patch.object(clipboard.pyperclip, "paste", side_effect=lambda: memory["value"]), \
             mock.patch.object(clipboard.threading, "Timer") as timer_factory:
            self.assertTrue(clipboard.copy_to_clipboard("synthetic-one"))
            old_callback = timer_factory.call_args.args[1]
            old_generation = timer_factory.call_args.kwargs["args"][0]
            self.assertTrue(clipboard.copy_to_clipboard("synthetic-two"))
            old_callback(old_generation)
            self.assertEqual(memory["value"], "synthetic-two")
            self.assertEqual(clipboard._last_secret, "synthetic-two")
            clipboard.clear_now()
            self.assertEqual(memory["value"], "")

    def test_lock_and_shutdown_cancel_stale_callbacks(self):
        memory = {"value": ""}
        with mock.patch.object(clipboard.pyperclip, "copy", side_effect=lambda value: memory.__setitem__("value", value)), \
             mock.patch.object(clipboard.pyperclip, "paste", side_effect=lambda: memory["value"]), \
             mock.patch.object(clipboard.threading, "Timer") as timer_factory:
            self.assertTrue(clipboard.copy_to_clipboard("synthetic-secret"))
            callback = timer_factory.call_args.args[1]
            generation = timer_factory.call_args.kwargs["args"][0]
            clipboard.clear_now()
            self.assertEqual(memory["value"], "")
            self.assertTrue(clipboard.copy_to_clipboard("new-synthetic-secret"))
            callback(generation)
            self.assertEqual(memory["value"], "new-synthetic-secret")
            clipboard.clear_now()
            callback(generation)
            self.assertEqual(memory["value"], "")


class FilesystemSafetyTests(unittest.TestCase):
    def test_writable_probe_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_synthetic_probe_", dir=Path(__file__).parent) as folder:
            marker = Path(folder, ".write_test")
            marker.write_text("synthetic existing file", encoding="utf-8")
            self.assertTrue(paths._is_writable(folder))
            self.assertEqual(marker.read_text(encoding="utf-8"), "synthetic existing file")

    def test_settings_save_does_not_follow_fixed_temp_path(self):
        with tempfile.TemporaryDirectory(prefix="nasolt_synthetic_settings_", dir=Path(__file__).parent) as folder:
            target = Path(folder, "settings.json")
            fixed_temp = Path(folder, "settings.json.tmp")
            fixed_temp.write_text("synthetic existing file", encoding="utf-8")
            with mock.patch.object(app_settings, "settings_file", return_value=str(target)):
                app_settings.save_settings({"autolock_minutes": 15})
            self.assertEqual(fixed_temp.read_text(encoding="utf-8"), "synthetic existing file")
            self.assertIn('"autolock_minutes": 15', target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
