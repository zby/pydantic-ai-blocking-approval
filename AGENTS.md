# AGENTS.md — Command Reference for AI Agents

Commands and gotchas that trip up AI agents. See `README.md` for architecture and usage patterns.

---

## Commands

### Python & Testing

```bash
# Run tests (NOT pytest directly)
uv run pytest

# Run a script (NOT python directly)
uv run python script.py

# Add dependency
uv add package_name

# Add dev dependency
uv add --dev package_name
```

**Why `uv run`?** This project uses `uv` for dependency management. Running `pytest` or `python` directly will fail or use wrong environment.

### Git

```bash
# Stage specific files (NOT git add -A or git add .)
git add path/to/file.py

# Always review before staging
git status
git diff

# Commit with clear message
git commit -m "feat: add approval caching for session decisions"
```

**Why no `git add -A`?** Blindly staging everything catches unintended files (temp files, debug prints, unrelated changes). Review `git status` first.

---

## Style

- Type hints required on all functions
- Pydantic models for data classes
- Delete dead code; don't preserve backwards compatibility
- Keep it simple; avoid over-engineering

---

## Quick Pitfalls

- `PermissionError` is raised on denial — handle gracefully
- Session cache key is `(tool_name, tool_args)` — identical args = cached
- Tests use mocks, no live API calls
