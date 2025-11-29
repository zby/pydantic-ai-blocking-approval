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
| `types.py` | Core data types: `ApprovalRequest`, `ApprovalDecision`, `ApprovalPresentation` |
| `memory.py` | Session cache for "approve for session" decisions |
| `protocol.py` | `ApprovalConfigurable` and `PresentableForApproval` protocols |
| `toolset.py` | `ApprovalToolset` wrapper that intercepts tool calls |
| `controller.py` | `ApprovalController` with mode-based behavior |
| `decorator.py` | `@requires_approval` marker decorator |

---

## Integration Patterns

1. **Simple**: Add tool names to `require_approval` list — always prompts with default presentation
2. **Custom logic**: Implement `needs_approval(tool_name, args) -> bool` on your toolset
3. **Custom presentation**: Implement `present_for_approval(tool_name, args) -> dict`
4. **Full control**: Use `ApprovalController` with modes for different environments

---

## Git Discipline

- **Never** `git add -A` — review `git status` and stage specific files
- Check `git diff` before committing
- Write clear commit messages (why, not just what)

---

## Common Pitfalls

- Forgetting to pass `memory` to `ApprovalToolset` disables session caching
- The `payload` in presentation determines cache key granularity — design it carefully
- `PermissionError` is raised on denial; callers should handle this gracefully
- `prompt_fn` blocks execution — ensure it returns promptly in non-interactive modes
- Tools NOT in `require_approval` list skip approval entirely (unless decorated)

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
