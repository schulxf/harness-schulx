# Contributing

Harness Schulx is intentionally small: one Python CLI, focused tests and no
runtime dependencies.

## Development Setup

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest tests/
```

## Before Changing Behavior

1. Read `README.md`.
2. Read `docs/HARNESS_PROTOCOL.md`.
3. Add or update tests.
4. Keep generated `.harness/` output out of git.

## Test Commands

```powershell
python -m ruff check .
python -m compileall -q bin .github\scripts tests
python -m pytest tests/
```

## Style

- Prefer deterministic local behavior.
- Keep runtime dependencies at zero unless there is a strong reason.
- Preserve old contracts where possible.
- Do not auto-approve tasks.
- Do not make the implementer self-approve.
- Keep P0/P1 fixes inside the same task.
- Review spelling, accentuation and clarity of PT-BR text before marking the PR
  checklist.
- Explain each PR in plain language so a reader does not need implementation
  jargon to understand what changed.
