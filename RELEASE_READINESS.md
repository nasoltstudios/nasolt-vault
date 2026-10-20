# Source update readiness — Phase A.5

Scope: the next update to the existing public source repository. The published `main` commit is `3f88d8a4e163d9b639977c81eceaf38b8ee7e628`; the remote was checked on 2026-10-21 and still points to that commit. No Phase A changes have been committed or pushed.

## Source decision

The Phase A.1–A.4 source update is staged for owner review. The 28-file staged set passed filename, secret-signature, and whitespace checks. This is a focused code review and synthetic test run, not an independent security certification. The Windows executable and NSIS installer are not approved for distribution.

## Verification on Windows 11

- Full suite with disposable synthetic data and normal Windows desktop access: **118 run, 116 passed, 0 failed, 2 skipped**. Symlink creation was unavailable, and the synthetic hotkey window could not take foreground focus. The first sandboxed run failed because Windows denied tray registration and atomic file replacement; the rerun passed.
- `python -m compileall -q .`: passed.
- `python -m pip check`: passed with no broken requirements.
- `python main.py --selftest`: passed using disposable synthetic data.
- `git diff --check`: passed. Git emitted only line-ending conversion warnings.
- Regression tests cover quick-access authentication and revocation, changed vault files, mocked Windows Hello results, startup value and shortcut ownership, instance handoff, background tray lifecycle, legacy format compatibility, and VoiceKey removal.
- Native Windows Hello PIN/biometric gesture, an actual Windows sign-in/restart sequence, the one-file executable, and NSIS install/upgrade/uninstall were **not rerun in this audit**. The owner previously reported seven Phase A.4 manual smoke checks as passing; that is historical owner verification.

## Publication controls

GitHub's read-only API reported Private Vulnerability Reporting enabled on 2026-10-21. Keep `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `THIRD_PARTY_NOTICES.md`, the approved Nasolt Studios assets, Python source, synthetic tests, and development scripts. Do not stage `data/`, virtual environments, caches, logs, exports, build output, executables, installers, or local audit notes. Review the exact staged diff before any commit.

## Remaining limits

Windows Hello only reauthenticates an already-unlocked session; a fully locked vault requires the master password. Windows Shell controls cold-start hotkey delivery and can deny or conflict with it. Startup and shortcut cleanup now avoid altering entries that do not point to the current installation; moving a source folder can leave an old entry for manual removal. Clipboard clearing is best effort. Transitive dependency versions and binary redistribution notices need a separate review before any binary release.
