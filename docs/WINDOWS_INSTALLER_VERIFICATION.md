# Nasolt Vault 2.0.0 Windows release candidate

**Local build only. Do not distribute the executable or installer yet.** This
candidate starts from public `main` commit
`bf11e077f802f22da6df6d81e619fb2d90a01399` and includes the merged
legacy `.nsv` importer. It does not change the encrypted `NSLT` vault format.

## Verified locally on Windows 11

- Python 3.12.3 and pinned dependencies built the executable; its bundled
  self-test passed. Archive inspection found the `.nsv` importer, installer
  recovery helper, 57 app assets, and Python, Tcl/Tk, Roboto, NSIS, and other
  third-party notice files.
- NSIS 3.11 compiled the installer with no reported warnings. Its compiler log
  records the freshly built 29,867,938-byte executable as the installer payload.
- A visible, responsive executable window opened and exited cleanly with an
  isolated synthetic `NASOLT_DATA_DIR`. No personal vault was opened.
- Source tests: 161 run, 159 passed, 0 failed, 2 skipped. Synthetic fault
  injection covered interrupted upgrade, denied replacement, partial clean
  installation, foreign folder refusal, and byte-identical preservation of a
  fictional vault, backup, Lockout Lab sidecar, and settings. The new cleanup
  tests interrupted every deletion step for committed and restored upgrades
  and for committed clean installations. Recovery completed on retry without
  rolling back a committed program or leaving reserved files that block the
  next installation. Interruptions immediately before and after the atomic
  journal transition also recovered to the correct previous or committed state.
- Source and bundled headless self-tests, `compileall`, `pip check`, and pinned
  runtime/build `pip-audit` checks passed. The audits found no known
  vulnerabilities at the time of this check.

| Ignored local artifact | SHA-256 |
|---|---|
| `packaging/windows/artifacts/dist/Nasolt Vault.exe` | `5ECF45BBAE2112D291E709E49ABAD4CF54334DD75E545537F5DD496E22064BCF` |
| `packaging/windows/artifacts/installer/Nasolt_Vault_Setup_2.0.0.exe` | `A8201EBA27D7B81532128FADA612F0795292A1F63CA4B989FB46C07B66F3B4EB` |

## Installation checks still required

No disposable Windows VM or separate test account was available for running
this installer. **Real clean installation, upgrade, uninstall, reinstall,
shortcut and startup cleanup, and `.nsv` import from an installed copy are
UNVERIFIED.** The installer has not been run against the owner's account.
Real process termination during an upgrade is also UNVERIFIED; synthetic
fault injection is not a substitute. Both binaries are unsigned.

Use a disposable Windows VM with a snapshot, or a separate disposable
standard-user Windows account, for the minimum release check:

1. Verify the installer SHA-256 above. Install without administrator rights,
   create a fictional vault, add an entry, exit, reopen, and unlock it.
2. Import a fictional `.nsv` made by the original exporter. Check the password
   prompt, preview, confirmation, entries, groups, and wrong-password refusal.
3. Upgrade an older working Nasolt Vault build in that environment. Record
   SHA-256 hashes of synthetic `vault.enc`, `.bak`, `lockout_lab.enc`, its backup,
   and `settings.json` before and after; unlock the vault after upgrading.
4. Check owned and foreign shortcuts, tray Exit, startup registration, and
   uninstall. Confirm encrypted data remains, then reinstall and unlock it.
5. In a snapshotted VM only, interrupt setup during an upgrade and verify that
   rerunning setup restores or completes a working application without altering
   encrypted data. Revert the snapshot afterward.

Do not use actual vaults, exports, credentials, or backups for these checks.
Do not disable Windows security protections to run an unsigned build.
