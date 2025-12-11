# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2025-12-11

### Added

- Async callback support for web UI, Slack bots, and other async approval workflows
- `ApprovalCallback` type alias - accepts both sync and async callbacks
- `ApprovalController.request_approval()` - async method that handles both sync and async callbacks
- Detection uses `inspect.isawaitable()` on callback result for maximum flexibility

### Changed

- `ApprovalToolset._prompt_for_approval()` is now async internally
- `ApprovalController` accepts async callbacks via the existing `approval_callback` parameter

### Fixed

- `ApprovalController.request_approval_sync()` now raises `TypeError` if given an async callback
  - Previously would return an unawaited coroutine (silent bug)
  - Error message directs users to `request_approval()` for async callbacks

### Documentation

- Added `docs/design.md` - consolidated design documentation with async coverage
- Added `docs/case_for_core.md` - context on blocking vs deferred approval patterns

## [0.7.0] - 2025-12-03

### Added

- `ApprovalResult` - Structured result type for approval checking with three states:
  - `ApprovalResult.blocked(reason)` - Operation forbidden by policy
  - `ApprovalResult.pre_approved()` - No user prompt needed
  - `ApprovalResult.needs_approval()` - Requires user approval
- `SupportsApprovalDescription` - Protocol for toolsets that provide custom approval descriptions
- Blocked operations now raise `PermissionError` with the block reason

### Changed

- **BREAKING**: `SupportsNeedsApproval.needs_approval()` now returns `ApprovalResult` instead of `bool | dict`
  - Clearer semantics: three explicit states instead of overloaded return types
  - Blocked operations are now part of the return type, not exceptions
- **BREAKING**: Description generation is now a separate protocol (`SupportsApprovalDescription`)
  - `get_approval_description(name, tool_args, ctx)` returns the description string
  - If not implemented, `ApprovalToolset` generates a default description
- Internal refactoring of `ApprovalToolset`:
  - `_get_approval_result()` - Get approval status from inner toolset or config
  - `_get_description()` - Get description from inner toolset or generate default

### Migration

**Config-based approval** (no change needed):
```python
# Works the same as before
ApprovalToolset(inner=toolset, config={"safe_tool": {"pre_approved": True}})
```

**Custom approval logic** - update return types:
```python
# Old (0.5.0)
class MyToolset(AbstractToolset):
    def needs_approval(self, name, tool_args, ctx: RunContext) -> bool | dict:
        if blocked:
            raise PermissionError("reason")
        if safe:
            return False
        return {"description": "Execute command"}

# New (0.7.0)
class MyToolset(AbstractToolset):
    def needs_approval(self, name, tool_args, ctx: RunContext) -> ApprovalResult:
        if blocked:
            return ApprovalResult.blocked("reason")
        if safe:
            return ApprovalResult.pre_approved()
        return ApprovalResult.needs_approval()

    def get_approval_description(self, name, tool_args, ctx: RunContext) -> str:
        return "Execute command"
```

## [0.5.0] - 2025-12-03

### Added

- `SupportsNeedsApproval` - Protocol for toolsets with custom approval logic

### Changed

- **BREAKING**: `ApprovalToolset` now auto-detects inner toolset capabilities
  - If inner implements `SupportsNeedsApproval` protocol: delegates to `inner.needs_approval()`
  - Otherwise: uses `config` dict for `pre_approved` settings (same as 0.4.0)
- **BREAKING**: `SupportsNeedsApproval.needs_approval()` now receives `ctx: RunContext` as third parameter
  - Allows approval decisions based on run context (dependencies, user data, etc.)
- No API change for config-based usage (most common case)

### Migration

**Config-based approval** (no change needed):
```python
# Works the same in 0.4.0 and 0.5.0
ApprovalToolset(inner=toolset, config={"safe_tool": {"pre_approved": True}})
```

**Custom approval logic** - implement `SupportsNeedsApproval` on your inner toolset:
```python
# Old (0.4.0) - subclass ApprovalToolset
class MyApprovalToolset(ApprovalToolset):
    def needs_approval(self, name, tool_args):
        # custom logic

MyApprovalToolset(inner=BasicToolset(), ...)

# New (0.5.0) - implement protocol on inner toolset with ctx parameter
class MyToolset(AbstractToolset):
    def needs_approval(self, name, tool_args, ctx: RunContext):
        # custom logic, can use ctx.deps for user-specific decisions

ApprovalToolset(inner=MyToolset(), approval_callback=callback)
```

## [0.4.0] - 2025-11-30

### Removed

- **BREAKING**: Removed `@requires_approval` decorator
  - Config is now the single source of truth for pre-approval
  - Default behavior is "require approval" (secure by default)
- **BREAKING**: Removed `ApprovalConfigurable` protocol
  - Inner toolset no longer needs awareness of approval
  - Custom approval logic should subclass `ApprovalToolset` instead
- **BREAKING**: Removed `protocol.py` and `decorator.py` modules

### Changed

- **BREAKING**: Replaced `pre_approved: list[str]` parameter with `config: dict[str, dict]`
  - Old: `ApprovalToolset(inner=toolset, pre_approved=["tool_a", "tool_b"])`
  - New: `ApprovalToolset(inner=toolset, config={"tool_a": {"pre_approved": True}})`
  - Per-tool configuration allows future extension with additional settings
- **BREAKING**: Made `needs_approval()` a public method on `ApprovalToolset`
  - Subclass `ApprovalToolset` and override `needs_approval()` for custom logic
  - Default implementation checks `config[tool_name]["pre_approved"]`
  - Inner toolset no longer implements `needs_approval()` — that's the wrapper's job
- Secure by default: tools not in config require approval

### Migration

From `pre_approved` list:
```python
# Old (0.3.0)
ApprovalToolset(inner=toolset, pre_approved=["tool_a", "tool_b"])

# New (0.4.0)
ApprovalToolset(
    inner=toolset,
    config={"tool_a": {"pre_approved": True}, "tool_b": {"pre_approved": True}},
)
```

From inner `needs_approval()`:
```python
# Old (0.3.0): inner toolset implements needs_approval()
class MyToolset(AbstractToolset):
    def needs_approval(self, name, args):
        # custom logic

ApprovalToolset(inner=MyToolset(), ...)

# New (0.4.0): subclass ApprovalToolset instead
class MyApprovalToolset(ApprovalToolset):
    def needs_approval(self, name, tool_args):
        # custom logic (same as before)

MyApprovalToolset(inner=BasicToolset(), ...)
```

## [0.3.0] - 2025-11-30

### Removed

- **BREAKING**: Removed `ApprovalPresentation` type entirely
  - Presentation is now the CLI's responsibility
  - The CLI can use `tool_name` to look up rendering logic

### Changed

- **BREAKING**: Renamed `ApprovalRequest.payload` to `ApprovalRequest.tool_args`
  - Simpler: just pass the tool arguments directly, no separate payload
  - Session cache key is now `(tool_name, tool_args)`
- Simplified `needs_approval()` return dict
  - Only `description` key is used (for custom approval message)
  - Removed `payload` key - tool_args are used for caching

## [0.2.0] - 2024-11-30

### Changed

- **BREAKING**: Renamed `require_approval` parameter to `pre_approved` in `ApprovalToolset`
  - Old: tools in list required approval, others skipped
  - New: tools in list skip approval, others require it (secure by default)
- **BREAKING**: Merged `present_for_approval()` into `needs_approval()`
  - `needs_approval()` now returns `bool | dict` instead of just `bool`
  - Return `False` to skip approval
  - Return `True` for approval with default presentation
  - Return `dict` for approval with custom presentation (description, payload, presentation)
- **BREAKING**: Removed `PresentableForApproval` protocol

### Added

- `ApprovalMemory.list_approvals()` - enumerate all cached session approvals
- `ApprovalMemory.__len__()` - get count of cached approvals
- `ShellToolset` example in tests demonstrating pattern-based approval
- Design documentation (`docs/notes/design_motivation.md`)
- User stories documentation (`docs/notes/cli_approval_user_stories.md`)
- GitHub Actions CI for Python 3.12, 3.13, 3.14
- `py.typed` marker for type checker support

## [0.1.0] - 2024-11-29

### Added

- Initial release
- `ApprovalToolset` - wrapper for PydanticAI toolsets with approval checking
- `ApprovalController` - mode-based controller (interactive/approve_all/strict)
- `ApprovalMemory` - session cache for "approve for session" functionality
- `ApprovalRequest`, `ApprovalDecision`, `ApprovalPresentation` types
- `@requires_approval` decorator
- `ApprovalConfigurable` protocol for custom approval logic
