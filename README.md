<p align="center">
  <img src="assets/nasolt-studios-logo.jpg" alt="Nasolt Studios logo" width="180">
</p>

# Nasolt Vault

Nasolt Vault is a free, open-source password manager for Windows by Nasolt Studios. It runs locally with Python and CustomTkinter. Your vault and optional recovery map stay on your device; the app does not use a server, AI, or telemetry.

**Current distribution:** public source code only. Windows executable and NSIS installer builds are under verification and are not approved for distribution. Run the application from source using the instructions below. Linux and macOS are not supported.

## Features

- Create and unlock a vault with a master password; add, edit, search, group, and delete entries.
- Generate passwords, estimate their strength, and copy them with optional timed clipboard clearing.
- Lock the vault manually or after inactivity. Encrypted backups and explicit backup recovery help protect against interrupted or damaged saves.
- Export and import entries and groups in password-protected `.nve` files. CSV and JSON are available as plaintext compatibility formats with an export warning.
- Use offline account icons and a live icon preview when adding an entry.
- Map recovery dependencies with **Lockout Lab**, an optional section described below.
- Open **Vault Summon** after fresh master-password or enrolled Windows Hello session verification for compact search and timed clipboard copies.

## Vault Summon

Choose **Tools → Vault Summon** or press **Ctrl+Alt+N**. A compact prompt asks for the master password. If the vault was fully locked, this decrypts it and opens Summon directly; the main window stays hidden when it started in the tray. If the vault was already unlocked, the prompt reauthenticates the current session. Search account names, usernames, and URLs, then select an account to copy its username or password. Passwords are never shown in the popup. Copies use the existing timed clipboard clear. The popup closes after password copy or its configurable inactivity timeout. Vault locking closes quick access.

On Windows 11, Settings can optionally enroll **Windows Hello** for reauthentication while the vault is already unlocked. Enrollment requires the current master password and successful native Windows Hello verification. After enrollment, use the Hello button in the compact prompt or set **Prefer Hello** for Ctrl+Alt+N. Windows chooses the available PIN, face, or fingerprint gesture. Canceling or failing Hello leaves the master-password option available. A fully locked vault **still requires its master password**: Hello consent alone does not recover the vault key. Enrollment stores only authenticated, nonsecret preferences in `hello-enrollment.json`; it does not store a password or vault key. Remove enrollment in Settings. Windows Hello support requires Windows build 22000 or later and a configured device.

**Ctrl+Alt+N** is enabled by default while Nasolt Vault is running. Settings can change or disable the shortcut. Windows reserves an enabled global chord; Shift+letter alternatives can interrupt ordinary uppercase typing. Settings reports when registration is denied or another application uses the chord. The running app uses Windows `RegisterHotKey`, without a keyboard hook. Input-desktop detection is best effort.

On Windows, **Start with Windows** is on by default after the first normal launch. It uses a per-user startup entry and opens cryptographically locked in the system tray without administrator rights. Closing the window locks the vault and leaves the app in the tray by default. The tray offers **Open Vault**, **Lock Vault**, **Settings**, and **Exit**; Exit stops the process. Both options can be disabled in Settings. The optional **Cold-start shortcut** is off by default: it creates a per-user Start Menu shortcut for Ctrl+Alt+N that asks Windows Shell to launch the app from a fully exited state. Windows Shell hotkey delivery depends on the user's desktop and can conflict with other shortcuts. Disabling this option removes a shortcut only when it points to the current installation. A shortcut left by a moved source folder may need manual removal.

## Run from source on Windows

Install Python 3.12, then open PowerShell in the project folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

If the `py` launcher is unavailable, use `python -m venv .venv` with a Python 3.12 installation. Package installation requires internet access; normal vault operation is offline. The GUI and source tests have been exercised on Windows 11 with Python 3.12.3.
After updating an existing checkout, rerun `python -m pip install -r requirements.txt` inside its virtual environment so updated security pins are applied.

Run the source checks with fictional data in a disposable `NASOLT_DATA_DIR`:

```powershell
$env:NASOLT_DATA_DIR = Join-Path $env:TEMP ("nasolt-source-tests-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $env:NASOLT_DATA_DIR | Out-Null
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m compileall -q .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py --selftest
```

For isolated manual testing without PowerShell, double-click [Run_Nasolt_Vault_Test.bat](Run_Nasolt_Vault_Test.bat). It creates a separate `.venv-test` environment and uses `%LOCALAPPDATA%\Nasolt Vault Test Data`, retaining that test data between launches. Use fictional accounts and passwords only. The launcher keeps its console open after the app exits so startup errors remain visible.

Windows source checks also run through [the CI workflow](.github/workflows/windows-source-tests.yml) on proposed changes and pushes to `main`. The workflow is newly prepared and its hosted-runner result is not yet verified. Local packaging instructions are in [packaging/windows](packaging/windows/README.md); builds stay in ignored `artifacts/windows/` and remain unapproved for distribution.

A normal source run uses `data/` beside the source when writable. `NASOLT_DATA_DIR` overrides the data location. Keep a separate encrypted copy of the **whole** data folder before changing installations or testing new builds. See [RELEASE_READINESS.md](RELEASE_READINESS.md) for the current source and binary verification status.

## Lockout Lab

After unlocking, open **Lockout Lab** to map accounts, devices, and recovery methods. A route can require several items together (**AND**); additional routes provide alternatives (**OR**). Mark a method **Documented** when you have recorded where to find it, or **User-verified** only after you have tested it yourself. Never enter passwords or recovery-code values into the map.

Simulate a **lost phone**, **inaccessible primary email**, or **lost computer**. The results identify potentially blocked routes, unknown dependencies, and circular relationships, with preparation steps in plain language. Results are based on your map; the app does not contact providers or verify that a provider will accept a recovery method.

Lockout Lab metadata is stored separately in encrypted `lockout_lab.enc` and requires an unlocked vault session. Entry exports do not include this file, so a complete backup must include the whole data folder.

## Security and data handling

The existing `NSLT` vault format is version 1. Nasolt Vault derives a key from the master password with Argon2id and encrypts vault contents with AES-256-GCM. The app does not store the master password, and there is no password reset. Keep your master password and encrypted backups safe. Windows Hello only reauthenticates an already-unlocked session; it cannot decrypt a locked vault.

Password-protected `.nve` exports use Argon2id and authenticated AES-256-GCM encryption with a separate export password. That password is required to import the file. `.nve` is an entry export, not a replacement for a full vault backup; it excludes Lockout Lab data, settings, and backup generations. Compatibility with encrypted exports from older, unidentified implementations has not been established.

**CSV and JSON exports contain readable passwords.** Store them carefully and remove them when no longer needed. Clipboard clearing is best effort; other applications and clipboard history may retain copies. Local logs may contain paths or other diagnostic context; review them before sharing. App-instance locking coordinates cooperating copies of Nasolt Vault, but it cannot protect against malware, a compromised device, or external tools modifying files.

## Project information

- [MIT License](LICENSE) — Copyright (c) 2026 Nasolt Studios
- [Security policy](SECURITY.md) — report vulnerabilities privately
- [Contributing guide](CONTRIBUTING.md) — use synthetic data and run source checks
- [Third-party notices](THIRD_PARTY_NOTICES.md) — dependency and icon attributions
- [Architecture](docs/ARCHITECTURE.md), [threat model](docs/THREAT_MODEL.md), and [Windows release checklist](docs/RELEASE_CHECKLIST.md)
- [Future full Windows Hello unlock proposal](docs/WINDOWS_HELLO_FULL_UNLOCK_PROPOSAL.md) — **unimplemented**

No application screenshots are included until screenshots made with fictional data are reviewed and approved. The Windows executable and installer remain unverified and must not be distributed.
