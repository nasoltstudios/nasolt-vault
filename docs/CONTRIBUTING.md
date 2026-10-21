# Contributing

Use a disposable directory and synthetic vault data for development and tests.
Never submit real vault files, passwords, recovery codes, plaintext exports, or
unreviewed logs and screenshots. Report vulnerabilities through the private
route in [SECURITY.md](SECURITY.md).

Before a pull request, run:

```powershell
$env:NASOLT_DATA_DIR = Join-Path $env:TEMP ("nasolt-contributor-tests-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $env:NASOLT_DATA_DIR | Out-Null
python -m pip install -r packaging/requirements.txt
python -m pip install -e src --no-deps
python -m unittest discover -s tests -q
python -m compileall -q -x '(artifacts|[.]venv)' src/nasolt_vault tests packaging
python -m pip check
python -m nasolt_vault --selftest
```

Describe the behavior changed, test evidence, and compatibility impact. Keep
the `NSLT` vault format and master-password behavior compatible with existing
vaults. Any format change needs an explicit migration and rollback plan. Keep
Lockout Lab optional and offline; simulation inputs must never include password
or recovery-code values.

Do not commit local `packaging/windows/artifacts/` output, vault sidecars, logs, test environments,
or binary installers. Windows CI is configured in `.github/workflows/` but
does not replace actual desktop testing for a binary release.
