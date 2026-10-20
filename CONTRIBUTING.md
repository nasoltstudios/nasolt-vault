# Contributing

Use a disposable directory and synthetic vault data for development and tests.
Never submit real vault files, passwords, recovery codes, plaintext exports, or
unreviewed logs and screenshots. Report vulnerabilities through the private
route in [SECURITY.md](SECURITY.md).

Before a pull request, run:

```powershell
python -m unittest discover -s tests -q
python -m compileall -q .
```

Describe the behavior changed, test evidence, and compatibility impact. Keep
the `NSLT` vault format and master-password behavior compatible with existing
vaults. Any format change needs an explicit migration and rollback plan. Keep
Lockout Lab optional and offline; simulation inputs must never include password
or recovery-code values.
