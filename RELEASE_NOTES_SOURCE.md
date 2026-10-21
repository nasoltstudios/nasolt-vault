# Phase B.0 source changes — prepared, unpublished

This proposed source update hardens vault-session and clipboard concurrency, removes predictable temporary-file names from settings and folder probing, organizes Windows packaging under `packaging/windows/` with root build-command compatibility, adds Windows source CI, and documents architecture, threat boundaries, and binary-release requirements. Existing NSLT vault files and master passwords require no migration.

The Windows executable and NSIS installer are **not approved for distribution**. No Linux or macOS package is provided. Final test counts and any unresolved findings belong in the owner review report, not in this pre-verification note. No commit, push, tag, or GitHub release has been made for these changes.
