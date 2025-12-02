# AGENTS.md — Field Guide for AI Agents

Key expectations that frequently trip up automation agents. See `README.md` for setup and usage.

---

## Key References

- `README.md` — package overview, installation, usage patterns
- `src/pydantic_ai_blocking_approval/` — source modules
- `tests/` — test suite with usage examples

---

## Development

- Run `uv run pytest` before committing (tests use mocks, no live API calls)
- For executing python scripts use `uv run python`
- Style: PEP 8, type hints required, Pydantic models for data classes
- Do not preserve backwards compatibility; prioritize cleaner design
- Favor clear architecture over hacks; delete dead code when possible

---

## Module Responsibilities

| Module | Purpose |
|--------|---------|
| `types.py` | Core data types: `ApprovalRequest`, `ApprovalDecision` |
| `memory.py` | Session cache for "approve for session" decisions |
| `toolset.py` | `BaseApprovalToolset` (abstract), `SimpleApprovalToolset` (config-based), `ApprovalToolset` (delegating) |
| `controller.py` | `ApprovalController` with mode-based behavior |

---

## Integration Patterns

1. **Simple (config-based)**: Use `SimpleApprovalToolset` with `config={"tool_name": {"pre_approved": True}}` — all others require approval (secure by default)
2. **Delegating**: Use `ApprovalToolset` when inner toolset implements `needs_approval(name, tool_args)`
   - Return `False` to skip approval
   - Return `True` for default presentation
   - Return `dict` with custom description (`{"description": "..."}`)
3. **Full control**: Use `ApprovalController` with modes for different environments

---

## Git Discipline

- **Never** `git add -A` — review `git status` and stage specific files
- Check `git diff` before committing
- Write clear commit messages (why, not just what)

---

## Common Pitfalls

- Forgetting to pass `memory` to `ApprovalToolset` disables session caching
- Session cache key is `(tool_name, tool_args)` — identical args = cached approval
- `PermissionError` is raised on denial; callers should handle this gracefully
- `approval_callback` blocks execution — ensure it returns promptly in non-interactive modes
- Tools with `config[name]["pre_approved"]=True` skip approval (secure by default: unlisted tools require approval)

---

## Testing Modes

```python
# For unit tests - auto-approve everything
controller = ApprovalController(mode="approve_all")

# For security tests - verify all dangerous ops are blocked
controller = ApprovalController(mode="strict")
```

---

Stay focused, stay type-safe, trust the blocking flow.
