# Release Checklist

Use this before publishing a new version.

## Local Verification

```powershell
python -m ruff check .
python -m compileall -q bin .github\scripts tests
python -m pytest tests/
python -m pip install -e .
harness-schulx --version
python bin\harness.py --version
python bin\harness.py --help
```

## Repository Hygiene

- No secrets in committed files.
- `.harness/` ignored in this repository.
- `__pycache__/` and `.pytest_cache/` ignored.
- README updated.
- Skill copy updated in `skills/harness-runner/SKILL.md`.
- Bundled skills have valid frontmatter, referenced files and license notices.
- v0.3 protocol docs updated.
- Telegram remote-control docs updated.
- Dashboard, pixel-art hub, queue, supervisor, resume/checkpoint, GitHub helper,
  budget, artifact, memory, plugin and security scanner docs checked for
  consistency.
- Tests updated for new behavior.
- PR body has a short plain-language summary.
- PT-BR spelling, accentuation and clarity checkbox is checked only after review.

## GitHub

```powershell
git status
git add .
git commit -m "Release v0.3.0"
git push -u origin main
```

## After Push

- Check GitHub Actions.
- Check README rendering.
- Verify clone instructions from a clean directory.
