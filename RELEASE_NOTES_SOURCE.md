# Source update notes — prepared, unpublished

Proposed commit: `feat: add Vault Summon and Windows Hello quick access`

This update is for the existing public source repository. No commit, push, tag, GitHub release, executable, or installer is part of this preparation.

## Changes

- **Vault Summon:** Ctrl+Alt+N opens a compact account search after fresh master-password authentication. For an already-unlocked vault, optional Windows Hello can reauthenticate the current session. A fully locked vault still requires the master password. Passwords are copied on request, never displayed in the popup.
- **Background operation:** optional per-user Windows startup defaults on and begins locked in the tray. The tray offers Open Vault, Lock Vault, Settings, and Exit. Closing the window locks the vault and keeps the app in the tray by default. An optional Start Menu shortcut can request Ctrl+Alt+N cold start where Windows Shell delivers it.
- **Session safeguards:** quick access is revoked on lock, Windows desktop change, session-file mismatch, and exit. Startup registry values and Start Menu links are removed only when they point to the current installation.
- **VoiceKey removal:** the experimental preview, Ctrl+Alt+V registration, UI, and microphone path are gone. Legacy settings are ignored and app-owned legacy shortcuts are cleaned up conservatively.
- **Presentation and diagnostics:** refreshed Windows XP-style login, visible modal action buttons, and expanded headless import checks.

## Verification and limits

On Windows 11, 118 synthetic source tests ran: 116 passed, 0 failed, 2 skipped. Compileall, dependency integrity, headless self-test, and Git whitespace checks passed. Native Windows Hello gestures and a full sign-in/restart sequence were not rerun in this audit; the owner previously reported seven manual Phase A.4 smoke checks as passing. The executable and NSIS installer remain unverified for distribution. No vault-file format migration is introduced.
