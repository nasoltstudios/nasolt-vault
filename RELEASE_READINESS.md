# Source publication checklist

Scope: public **source only**. No repository, tag, release, executable, or
installer has been published. The Windows executable and NSIS installer remain
unverified and must not be distributed.

## Include

`LICENSE`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`,
`THIRD_PARTY_NOTICES.md`, `RELEASE_NOTES_SOURCE.md`,
`requirements.txt`, `.gitignore`, the Python source at the root and in `ui/`,
the synthetic tests in `tests/`, `assets/app.ico`, `assets/app.png`,
the owner-supplied `assets/nasolt-studios-logo.jpg`,
`assets/app_icons/`,
`assets/brands.json`, `assets/icons/`, `third_party_licenses/`,
`tools/make_icon.py`, and the developer build/installer scripts and
`installer/installed.flag`. `Run_Nasolt_Vault_Test.bat` is the source test
launcher; it creates no distributable binary.

## Exclude

Local audit working notes (`SECURITY_AUDIT_PHASE_1*.md`), the outdated
`CHANGELOG.md`, the retired asset
fetcher (`tools/fetch_assets.py`), caches, virtual environments, build output,
binary installers/executables, logs, exports (`.nve`, `.csv`, `.json`), encrypted user data, credentials,
and any generated or personal files. The original unverified brand images and
app JPG have been removed. This folder had no existing Git repository or local
history to review; use a new empty GitHub repository and do not import an
unreviewed history.

## Remaining publication step

Enable GitHub Private Vulnerability Reporting immediately after creating the
repository and before inviting public issue reports. Verify the remote is
empty, review `git diff --cached --name-only`, and push only the staged source
set. No binary release is approved.

## Final local checks

- Windows / Python 3.12.3: 75 tests ran; 74 passed, 0 failed, 1 skipped
  because symlink creation was unavailable in the test environment.
- `python -m compileall -q .`, `python -m pip check`, and the headless
  `python main.py --selftest` all passed. The self-test used a disposable temp
  folder inside `tests/` because the sandbox's default Windows temp location
  denied file replacement.
- CustomTkinter printed a bundled shape-font load warning and used its fallback
  renderer in this environment. GUI startup and interaction tests still passed.
- A disposable synthetic GUI smoke test confirmed that an open Lockout Lab
  page auto-locks, closes the vault session, and leaves the encrypted sidecar
  and vault unlockable afterward.
- Windows GUI tests exercised the entry dialog, account icon preview, XP-style
  slider input, and encrypted import/export. Callback cleanup on fast login
  swaps, vault locking, and tooltip teardown was also checked. Encrypted export round trips,
  wrong passwords, tampering, truncation, and failed writes were also checked
  with synthetic data.
- The test launcher opened a visible and interactive window, closed cleanly,
  and reopened. A synthetic vault was created, closed, then unlocked on a
  second launch. Fresh virtual-environment creation succeeded; package
  installation in that disposable copy could not complete because this
  sandbox could not reach the package index.
- The staged source files had no high-confidence credential signatures,
  private-key headers, personal home paths, or forbidden user-data/binary
  filenames in the local scan. The new local Git repository has zero commits.

**Decision:** source-only publication is ready after the owner enables private
vulnerability reporting on the new GitHub repository. Windows executable and
installer distribution remain blocked by their unverified runtime behavior.
Earlier phase reports are retained locally and excluded because their
decisions are superseded.
