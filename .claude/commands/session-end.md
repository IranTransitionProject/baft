Check session status and end the current analyst session:

```bash
uv run baft session status
uv run baft session end -m "<summary of changes>"
```

`session end` commits only the `data/` directory — never infrastructure files. The `-m` message is required and becomes the git commit message on the baseline repo.
