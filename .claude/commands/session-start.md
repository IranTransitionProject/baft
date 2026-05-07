Run environment preflight checks and start an analyst session:

```bash
uv run baft preflight
uv run baft session start
```

`preflight` runs 10 validations (service health, silo config integrity, schema versions). Fix any failures before starting a session.
