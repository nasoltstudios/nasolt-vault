<p align="center">
  <img src="assets/nasolt-studios-logo.jpg" alt="Nasolt Studios logo" width="180">
</p>

# Nasolt Vault

Nasolt Vault is a free, open-source password manager for Windows by Nasolt Studios. It runs locally with Python and CustomTkinter. Your vault and optional recovery map stay on your device; the app does not use a server, AI, or telemetry.

**Current distribution:** source code only. The Windows executable and NSIS installer have not been approved for distribution. Run the application from source using the instructions below.

## Features

- Create and unlock a vault with a master password; add, edit, search, group, and delete entries.
- Generate passwords, estimate their strength, and copy them with optional timed clipboard clearing.
- Lock the vault manually or after inactivity. Encrypted backups and explicit backup recovery help protect against interrupted or damaged saves.
- Export and import entries and groups in password-protected `.nve` files. CSV and JSON are available as plaintext compatibility formats with an export warning.
- Use offline account icons and a live icon preview when adding an entry.
- Map recovery dependencies with **Lockout Lab**, an optional section described below.

## Run from source on Windows

Install Python 3.12, then open PowerShell in the project folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

If the `py` launcher is unavailable, use `python -m venv .venv` with a Python 3.12 installation. Package installation requires internet access; normal vault operation is offline. The GUI and source tests have been exercised on Windows 11 with Python 3.12.3.

For isolated manual testing without PowerShell, double-click [Run_Nasolt_Vault_Test.bat](Run_Nasolt_Vault_Test.bat). It creates a separate `.venv-test` environment and uses `%LOCALAPPDATA%\Nasolt Vault Test Data`, retaining that test data between launches. Use fictional accounts and passwords only. The launcher keeps its console open after the app exits so startup errors remain visible.

A normal source run uses `data/` beside the source when writable. `NASOLT_DATA_DIR` overrides the data location. Keep a separate encrypted copy of the **whole** data folder before changing installations or testing new builds. See [RELEASE_READINESS.md](RELEASE_READINESS.md) for the current source and binary verification status.

## Lockout Lab

After unlocking, open **Lockout Lab** to map accounts, devices, and recovery methods. A route can require several items together (**AND**); additional routes provide alternatives (**OR**). Mark a method **Documented** when you have recorded where to find it, or **User-verified** only after you have tested it yourself. Never enter passwords or recovery-code values into the map.

Simulate a **lost phone**, **inaccessible primary email**, or **lost computer**. The results identify potentially blocked routes, unknown dependencies, and circular relationships, with preparation steps in plain language. Results are based on your map; the app does not contact providers or verify that a provider will accept a recovery method.

Lockout Lab metadata is stored separately in encrypted `lockout_lab.enc` and requires an unlocked vault session. Entry exports do not include this file, so a complete backup must include the whole data folder.

## Security and data handling

The existing `NSLT` vault format is version 1. Nasolt Vault derives a key from the master password with Argon2id and encrypts vault contents with AES-256-GCM. The app does not store the master password, and there is no password reset. Keep your master password and encrypted backups safe.

Password-protected `.nve` exports use Argon2id and authenticated AES-256-GCM encryption with a separate export password. That password is required to import the file. `.nve` is an entry export, not a replacement for a full vault backup; it excludes Lockout Lab data, settings, and backup generations. Compatibility with encrypted exports from older, unidentified implementations has not been established.

**CSV and JSON exports contain readable passwords.** Store them carefully and remove them when no longer needed. Local logs may contain paths or other diagnostic context; review them before sharing. App-instance locking coordinates cooperating copies of Nasolt Vault, but it cannot protect against malware, a compromised device, or external tools modifying files.

## Project information

- [MIT License](LICENSE) — Copyright (c) 2026 Nasolt Studios
- [Security policy](SECURITY.md) — report vulnerabilities privately
- [Contributing guide](CONTRIBUTING.md) — use synthetic data and run source checks
- [Third-party notices](THIRD_PARTY_NOTICES.md) — dependency and icon attributions

No application screenshots are included until screenshots made with fictional data are reviewed and approved. The Windows executable and installer remain unverified and must not be distributed.
