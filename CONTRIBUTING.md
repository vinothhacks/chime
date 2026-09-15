# Contributing

## Setup

```bash
uv sync --group dev
uv run chime --help
uv run pytest -q
```

## Rules

- Domain code (`models`, `scheduler`, `time_utils`, `clock`, `errors`) must not import Textual, Typer, Rich, or platformdirs.
- No `datetime.now()` in the scheduler. Inject a clock.
- No `shell=True`.
- Claim an occurrence, persist, then ring — never the reverse.
- Tests use a fake clock and a temp `CHIME_DATA_DIR`.

## Quality gates

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest -q
```
