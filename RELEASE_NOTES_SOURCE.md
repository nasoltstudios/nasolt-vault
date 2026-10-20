# Source release notes — prepared, unpublished

Prepared for a source-only publication. No tag, binary, installer, or public repository has been created.

## Highlights

- Lockout Lab maps accounts, devices, and recovery methods with combined requirements and alternative routes. It simulates lost phone, inaccessible primary email, and lost computer scenarios entirely offline.
- Recovery results show potentially blocked accounts, missing information, circular dependencies, and practical preparation steps. A user-verified marker records a user's own test; it is not provider verification.
- Lockout Lab metadata is authenticated and encrypted in a separate file tied to the unlocked vault session. The existing vault envelope and master-password derivation are unchanged.
- Import / Export now defaults to password-protected `.nve` files. Legacy CSV and JSON are still supported with an explicit plaintext warning. The `.nve` format is a separate entry export and does not alter `vault.enc`.
- Account names show locally drawn, offline monogram icons when recognized; new-entry icon preview and generated fallback icons remain available without unlicensed brand artwork.
- Installer migration now stages and verifies ciphertext, retains the portable source, and refuses destination conflicts. The uninstaller no longer deletes user data.
- Unverified brand artwork and the prior app JPG have been removed. A project-generated app icon pack and local account icon fallback remain; Lucide/Feather notices are included.

## Known limitations

- The NSIS installer has not passed an isolated Windows install/upgrade/uninstall test and must not be distributed yet.
- The final one-file executable compiled but Windows Application Control blocked its self-test launch; it is not approved for distribution.
- The project source is MIT licensed by Nasolt Studios. The owner has not published a repository, tag, or GitHub release yet.
- Lockout Lab outcomes are models, not live recovery checks. The sidecar is not included in entry exports.
- Direct runtime dependency versions are pinned; transitive package wheels are not hash locked, and binary redistribution notices are incomplete.
- Actual historical personal vaults were not tested; compatibility tests use synthetic v1 fixtures.
