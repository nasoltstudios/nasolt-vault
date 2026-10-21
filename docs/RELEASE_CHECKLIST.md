# Windows binary release checklist

**Current result: NO-GO for executable and installer distribution.** Source tests and a build self-test are useful gates, but do not replace a clean desktop install/upgrade/uninstall test. Use a disposable Windows user or VM and fictional vault data for every item. Preserve and compare encrypted file hashes before and after each operation. Record Windows, Python, PyInstaller, and NSIS versions plus exact artifacts and SHA-256 hashes.

- [ ] Build the one-file executable from pinned requirements; run its `--selftest` and open its real GUI.
- [ ] Create and unlock a fictional master-password vault; verify save, restart, lock, and reopen.
- [ ] Verify Windows Hello enrollment, cancellation, successful reauthentication, and the master-password path after a fully locked state.
- [ ] Verify Vault Summon, hotkey conflict reporting, automatic lock, tray startup, tray Exit, and restart after Windows sign-in.
- [ ] Test first install into an empty profile and install over an older version with existing portable and installed synthetic vaults.
- [ ] Exercise same-name foreign Start Menu and desktop shortcuts: setup must not overwrite them, uninstall must not delete them, and valid older Nasolt links must remain usable through upgrade. Check links with altered target, arguments, working directory, icon, or hotkey, and verify unrelated Start Menu items survive uninstall.
- [ ] Verify encrypted vault, backup, Lockout Lab sidecars, settings, and logs remain intact through upgrade, uninstall, and reinstall. Test migration failure, busy vault, damaged source, and destination conflict.
- [ ] Test crash handling during save and restart recovery; verify the damaged primary is preserved before explicit backup recovery.
- [ ] Verify no plaintext export, test vault, log, executable, or installer is committed to Git.
- [ ] Inventory exact binary dependencies, bundled third-party notices, native libraries, fonts, Python and Tcl/Tk runtime licenses.
- [ ] Confirm artifact naming/version, code-signing decision, SHA-256 checksums, and independent owner approval before distribution.

See [Windows packaging](../packaging/windows/README.md) for local build commands. A source-only publication does not imply binary readiness.

## Owner's isolated installer verification

Use a disposable Windows user or VM that contains no personal vault. In a PowerShell window at the source root, obtain the official portable NSIS archive from [the NSIS project](https://sourceforge.net/projects/nsis/files/NSIS%203/3.11/nsis-3.11.zip/download), confirm its SHA-256 is `c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1`, and extract it to a user-owned folder. Then run:

```powershell
cmd /c packaging\windows\BUILD_WINDOWS.bat nopause
$nsis = 'C:\path\to\nsis-3.11\makensis.exe'
Push-Location packaging\windows
& $nsis /V2 NasoltVault.nsi
Pop-Location
Get-FileHash -Algorithm SHA256 -LiteralPath 'packaging\windows\artifacts\installer\Nasolt_Vault_Setup_2.0.0.exe'
```

Check the NSIS exit code and the output file before using it. In the disposable account, record PASS, FAIL, SKIPPED, or UNVERIFIED for each checklist item above. Create only fictional vault data; compare hashes and successful unlock of the encrypted vault and sidecars before upgrade, after uninstall, and after reinstall. Verify app-owned startup and shortcut registrations are removed. Do not distribute the installer while any data-preservation or cleanup result remains unverified.
