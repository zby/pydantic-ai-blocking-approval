# AGENTS.md

Blocking approval system for PydanticAI tools. See README.md for full docs.

## Commands

```bash
uv run pytest        # Run tests (NOT pytest directly)
uv run python x.py   # Run scripts (NOT python directly)
```

## Git

Stage specific files, not `git add -A`. Review `git status` first.

## Design

- Secure by default: unlisted tools require approval
- No backwards compatibility hacks; delete dead code
