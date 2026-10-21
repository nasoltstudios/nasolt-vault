# Phase C.0 source restructure — local owner review

Nasolt Vault is now an installable Python package under `src/nasolt_vault/`. Assets are package resources, and the tests, Windows build tools, documentation, and license notices have dedicated folders. Source launch uses `python -m nasolt_vault` after installing the pinned runtime requirements and the editable `src/` package.

The application continues to select an existing encrypted vault beside the original source root or installed executable. The `NSLT` format, master-password behavior, encrypted backup handling, Lockout Lab, exports, and Windows Hello metadata are unchanged. Synthetic compatibility tests cover the previous portable and installed data locations.

This restructure is submitted for source review. No executable or installer is approved for distribution. Linux and macOS packages are unsupported. Confirm Windows CI and GitHub metadata display before merging.
