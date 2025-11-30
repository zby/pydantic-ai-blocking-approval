# Config-Based Approval Spec

**Status:** Proposed
**Date:** 2025-11-30

## Summary

Add config-based default `needs_approval()` logic to `ApprovalToolset`, enabling simple toolsets to use approval without implementing custom approval logic.

## Motivation

### Current State

`ApprovalToolset` supports two mechanisms for approval decisions:

1. **`pre_approved` list** - tool names that skip approval entirely
2. **`needs_approval()` method** - inner toolset implements custom logic

```python
ApprovalToolset(
    inner=my_toolset,
    approval_callback=callback,
    pre_approved=["safe_tool_1", "safe_tool_2"],  # Skip approval
)
```

### Problem

For simple toolsets (e.g., custom user-defined tools), implementing `needs_approval()` is overkill. Users just want to say "this tool needs approval, that one doesn't" via config.

Currently, the only option is the `pre_approved` list, which:
- Only supports "skip approval" (no way to say "require approval")
- Doesn't integrate with per-tool config
- Has opposite semantics from `@requires_approval` decorator (confusing)

### Use Case: Custom Tools in llm-do

llm-do allows workers to define custom tools in `tools.py`. Users want to configure approval per-tool:

```yaml
custom_tools:
  calculate_stats:
    approval: required       # Always prompt
  send_notification:
    approval: none           # Never prompt (trusted)
  format_output: {}          # Use default (check @requires_approval)
```

The `CustomToolset` wrapping these functions shouldn't need to implement `needs_approval()`. The config should be enough.

### Consistency Goal

We want consistent approval config across all tool types:

| Tool Type | Current Config | Proposed Config |
|-----------|----------------|-----------------|
| Sandbox paths | `write_approval: true` | `approval: {write: required}` |
| Custom tools | `pre_approved` list | `approval: required\|none` |
| Shell commands | `action: approve` | `approval: required` |

The `approval` field should have the same semantics everywhere.

## Proposed Design

### New Parameter: `tool_configs`

Add `tool_configs` parameter to `ApprovalToolset`:

```python
class ApprovalToolset(AbstractToolset):
    def __init__(
        self,
        inner: AbstractToolset,
        approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
        pre_approved: Optional[list[str]] = None,      # DEPRECATED
        tool_configs: Optional[dict[str, dict]] = None,  # NEW
    ):
        """
        Args:
            inner: The toolset to wrap
            approval_callback: Called when approval is needed
            memory: Session cache for "approve for session"
            pre_approved: DEPRECATED - use tool_configs instead
            tool_configs: Per-tool configuration dict
                {
                    "tool_name": {
                        "approval": "required" | "none",
                        # future: other per-tool settings
                    }
                }
        """
```

### Default `needs_approval()` Logic

When inner toolset doesn't implement `needs_approval()`, `ApprovalToolset` provides default logic:

```python
def _check_needs_approval(self, tool_name: str, tool_args: dict) -> bool | dict:
    """Determine if approval is needed for this tool call.

    Priority:
    1. Inner toolset's needs_approval() - if implemented, use it
    2. tool_configs setting - explicit config wins
    3. @requires_approval decorator - check on tool function
    4. Default: no approval needed

    Returns:
        False: no approval needed
        True: approval needed (default description)
        dict: approval needed with custom description
    """
    # 1. Delegate to inner toolset if it has custom logic
    if hasattr(self._inner, "needs_approval"):
        result = self._inner.needs_approval(tool_name, tool_args)
        # Inner toolset made a decision
        if result is not False:
            return result
        # Inner returned False - could still check config/decorator
        # Or respect inner's decision entirely? (see Open Questions)

    # 2. Check explicit tool config
    config = self._tool_configs.get(tool_name, {})
    approval_setting = config.get("approval")

    if approval_setting == "none":
        return False
    if approval_setting == "required":
        return {"description": f"Tool call: {tool_name}"}

    # 3. Check @requires_approval decorator
    func = self._get_tool_function(tool_name)
    if func and getattr(func, '_requires_approval', False):
        return {"description": f"Tool call: {tool_name}"}

    # 4. Default: no approval needed
    return False
```

### Deprecate `pre_approved`

The `pre_approved` list becomes redundant - it's equivalent to:

```python
# Old way
ApprovalToolset(inner=toolset, pre_approved=["tool_a", "tool_b"])

# New way
ApprovalToolset(
    inner=toolset,
    tool_configs={
        "tool_a": {"approval": "none"},
        "tool_b": {"approval": "none"},
    }
)
```

Keep `pre_approved` for backwards compatibility but emit deprecation warning:

```python
def __init__(self, ..., pre_approved=None, tool_configs=None):
    if pre_approved is not None:
        warnings.warn(
            "pre_approved is deprecated, use tool_configs instead",
            DeprecationWarning
        )
        # Convert to tool_configs
        tool_configs = tool_configs or {}
        for name in pre_approved:
            tool_configs.setdefault(name, {})["approval"] = "none"

    self._tool_configs = tool_configs or {}
```

### Approval Values

| Value | Meaning |
|-------|---------|
| `"required"` | Always prompt for approval |
| `"none"` | Never prompt (pre-approved) |
| `None` / missing | Use default logic (check decorator, etc.) |

Future values could include:
- `"once_per_session"` - prompt once, then remember
- `"deny"` - block entirely (raise PermissionError)

## Examples

### Simple Custom Toolset (no needs_approval)

```python
class MyToolset(AbstractToolset):
    """Simple toolset - no needs_approval needed."""

    async def get_tools(self, ctx):
        return {...}

    async def call_tool(self, name, args, ctx, tool):
        return self._functions[name](**args)

# Wrap with config-based approval
approved = ApprovalToolset(
    inner=MyToolset(),
    approval_callback=my_callback,
    tool_configs={
        "dangerous_tool": {"approval": "required"},
        "safe_tool": {"approval": "none"},
        # other tools use default (check @requires_approval)
    }
)
```

### Toolset with Custom Logic (has needs_approval)

```python
class FileSandbox(AbstractToolset):
    """Complex toolset - implements needs_approval for path-based decisions."""

    def needs_approval(self, tool_name: str, tool_args: dict) -> bool | dict:
        path = tool_args.get("path")
        path_config = self._find_path_config(path)

        if tool_name == "write_file":
            if path_config.approval.write == "none":
                return False
            return {"description": f"Write to {path}"}

        return False

# ApprovalToolset delegates to inner.needs_approval()
approved = ApprovalToolset(
    inner=FileSandbox(config),
    approval_callback=my_callback,
    # tool_configs not needed - FileSandbox handles it
)
```

### Mixed: Override Inner Logic with Config

```python
# FileSandbox says write_file needs approval
# But we want to pre-approve it for this specific use case

approved = ApprovalToolset(
    inner=FileSandbox(config),
    approval_callback=my_callback,
    tool_configs={
        "write_file": {"approval": "none"},  # Override inner's decision
    }
)
```

**Open Question:** Should `tool_configs` override inner's `needs_approval()`?

Options:
- A) Config always wins (override inner)
- B) Inner always wins (config only for toolsets without needs_approval)
- C) Config can only make stricter (can require approval, can't skip it)

Recommendation: **Option A** - Config always wins. The wrapper owner should have final say.

## Migration Path

### Phase 1: Add tool_configs (backwards compatible)

- Add `tool_configs` parameter
- Keep `pre_approved` working (with deprecation warning)
- Add default `_check_needs_approval()` logic

### Phase 2: Update documentation

- Document new pattern
- Show migration examples

### Phase 3: Remove pre_approved (breaking change, next major version)

- Remove `pre_approved` parameter
- Update all examples

## Testing

### New Tests

```python
def test_tool_configs_required():
    """Tool with approval: required always prompts."""
    toolset = ApprovalToolset(
        inner=SimpleToolset(),
        approval_callback=tracking_callback,
        tool_configs={"my_tool": {"approval": "required"}}
    )
    # Call my_tool -> should trigger callback

def test_tool_configs_none():
    """Tool with approval: none never prompts."""
    toolset = ApprovalToolset(
        inner=SimpleToolset(),
        approval_callback=tracking_callback,
        tool_configs={"my_tool": {"approval": "none"}}
    )
    # Call my_tool -> should NOT trigger callback

def test_tool_configs_missing_uses_decorator():
    """Tool without config checks @requires_approval."""
    # decorated_tool has @requires_approval
    # undecorated_tool does not
    toolset = ApprovalToolset(
        inner=ToolsetWithDecoratedFunction(),
        approval_callback=tracking_callback,
        tool_configs={}  # No explicit config
    )
    # Call decorated_tool -> should trigger callback
    # Call undecorated_tool -> should NOT trigger callback

def test_tool_configs_overrides_inner_needs_approval():
    """Config overrides inner toolset's needs_approval."""
    inner = ToolsetThatRequiresApproval()  # needs_approval returns True
    toolset = ApprovalToolset(
        inner=inner,
        approval_callback=tracking_callback,
        tool_configs={"my_tool": {"approval": "none"}}  # Override
    )
    # Call my_tool -> should NOT trigger callback (config wins)

def test_pre_approved_deprecation_warning():
    """pre_approved emits deprecation warning."""
    with pytest.warns(DeprecationWarning):
        ApprovalToolset(
            inner=SimpleToolset(),
            approval_callback=callback,
            pre_approved=["tool_a"]
        )
```

## Summary

This change:

1. **Adds `tool_configs`** parameter for per-tool approval settings
2. **Provides default `needs_approval()` logic** so simple toolsets don't need to implement it
3. **Deprecates `pre_approved`** in favor of `tool_configs`
4. **Enables consistent config** across different tool types

The goal is to make approval configuration declarative and consistent, while still allowing complex toolsets to implement custom logic.
