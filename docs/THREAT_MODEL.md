# Threat model (source review, not a security certification)

## Protected assets and boundaries

Protected assets are the master password, derived vault key, account passwords, encrypted vault and backup bytes, encrypted Lockout Lab metadata, and sensitive export files. The main trust boundary is between ciphertext on disk and plaintext in an unlocked process. Windows clipboard, UI automation, the user's desktop session, filesystem permissions, and native Windows Hello are separate trust boundaries. The application has no server, telemetry, or runtime internet requirement.

The NSLT v1 vault uses Argon2id and AES-256-GCM authentication. A wrong master password or modified ciphertext fails authentication. A file lock coordinates cooperating vault sessions, and save checks for an unexpected primary change. Backup recovery is explicit. Windows Hello confirms a user gesture for an *already unlocked* session; it does not decrypt a locked vault. Lockout Lab sidecar data is encrypted with a key derived from the unlocked session. These statements describe the implemented design and covered tests, not resistance to every attack.

## Attacker capabilities considered

- Someone who obtains a copy of a locked vault or export can attempt offline password guesses. Master and export password strength therefore matter.
- Another local process can alter or replace files, race with application operations, or read clipboard content. Unique temporary names and fingerprint checks reduce accidental overwrite and detect some races; they do not make a compromised account safe.
- A same-user process can read memory, simulate UI input, interfere with Windows prompts, alter startup entries, or observe clipboard history. Nasolt Vault does not defend against this level of compromise.
- A filesystem failure or power loss can interrupt saves. Atomic replacement and encrypted backup generations reduce data loss but cannot guarantee recovery from disk failure or multiple damaged copies.

## Operational limits

Keep an independently verified encrypted backup of the entire data folder, including sidecars. `.nve` exports omit settings and Lockout Lab data; CSV and JSON exports are plaintext. Clipboard auto-clear is best effort and cannot erase copies retained by other software. Logs can contain paths and error types; review before sharing. Automatic Windows startup and global shortcuts rely on the current Windows user session and can be blocked or redirected by user-level system changes. Native Windows Hello, sign-in/restart behavior, one-file packaging, and installer upgrades need actual desktop verification before binary distribution. Linux and macOS are unsupported.

## Review priorities

Review any change to `crypto.py`, `vault.py`, `paths.py`, `lockout_lab.py`, `export.py`, `quick_access.py`, native Windows integration, or NSIS source with synthetic compatibility fixtures and manual data-preservation checks. Keep the NSLT format unchanged without a migration plan. See [Security policy](../SECURITY.md) for private vulnerability reporting.
