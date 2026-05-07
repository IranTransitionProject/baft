Run the unit test suite (no infrastructure required):

```bash
uv run pytest tests/ -v -m "not e2e and not deepeval"
```

For deepeval tests (needs Ollama + command-r7b):
```bash
uv run pytest tests/ -m deepeval -v
```

Validate all worker configs:
```bash
uv run heddle validate configs/workers/*.yaml
```
