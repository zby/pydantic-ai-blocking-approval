# Spec: Async Callback Support

## Summary

Add support for async approval callbacks to enable remote/async UI workflows while maintaining full backward compatibility with sync callbacks.

## Motivation

The library currently supports **sync blocking** callbacks for CLI/terminal use cases. However, async UIs (web dashboards, Slack bots, mobile apps) need to:

1. Send approval requests to a remote UI
2. Await responses without blocking threads
3. Resume execution exactly where it paused

The existing abstractions (`ApprovalResult`, `ApprovalDecision`, `ApprovalMemory`) are already correct - only the callback invocation mechanism needs to become async-aware.

## Requirements

### Functional

1. Accept async callbacks: `async def callback(request) -> ApprovalDecision`
2. Accept sync callbacks: `def callback(request) -> ApprovalDecision` (existing)
3. Auto-detect callback type and handle appropriately
4. Preserve all existing behavior for sync callbacks
5. Support nested tool calls with async approval (stack preserved via await)

### Non-Functional

1. Backward compatible - no breaking changes to existing API
2. Minimal code changes
3. No new dependencies

## Design

### Type Changes (types.py)

Add union type for callbacks that can be sync or async:

```python
from typing import Awaitable, Callable, Union

# Callback can return ApprovalDecision directly (sync) or via Awaitable (async)
ApprovalCallback = Callable[
    [ApprovalRequest],
    Union[ApprovalDecision, Awaitable[ApprovalDecision]]
]
```

Update `__init__.py` exports to include `ApprovalCallback`.

### Toolset Changes (toolset.py)

#### 1. Update `__init__` type hint

```python
def __init__(
    self,
    inner: AbstractToolset,
    approval_callback: ApprovalCallback,  # Updated type
    memory: Optional[ApprovalMemory] = None,
    config: Optional[dict[str, dict[str, Any]]] = None,
):
```

#### 2. Convert `_prompt_for_approval` to async

Current:
```python
def _prompt_for_approval(
    self, name: str, tool_args: dict[str, Any], description: str
) -> None:
```

New:
```python
async def _prompt_for_approval(
    self, name: str, tool_args: dict[str, Any], description: str
) -> None:
    """Prompt user for approval. Raises PermissionError if denied."""
    # Check session cache first
    cached = self._memory.lookup(name, tool_args)
    if cached is not None and cached.approved:
        return

    request = ApprovalRequest(
        tool_name=name,
        tool_args=tool_args,
        description=description,
    )

    # Call callback and await if necessary
    result = self._approval_callback(request)
    if inspect.isawaitable(result):
        decision = await result
    else:
        decision = result

    self._memory.store(name, tool_args, decision)

    if not decision.approved:
        raise PermissionError(
            f"User denied {name}: {decision.note or 'no reason given'}"
        )
```

#### 3. Update `call_tool` to await

```python
async def call_tool(
    self,
    name: str,
    tool_args: dict[str, Any],
    ctx: RunContext[Any],
    tool: Any,
) -> Any:
    """Intercept tool calls for approval checking."""
    result = self._get_approval_result(name, tool_args, ctx)

    if result.is_blocked:
        raise PermissionError(result.block_reason)

    if result.is_needs_approval:
        description = self._get_description(name, tool_args, ctx)
        await self._prompt_for_approval(name, tool_args, description)  # Now awaited

    return await self._inner.call_tool(name, tool_args, ctx, tool)
```

### Controller Changes (controller.py)

#### 1. Update `__init__` type hint

```python
def __init__(
    self,
    mode: Literal["interactive", "approve_all", "strict"] = "interactive",
    approval_callback: Optional[ApprovalCallback] = None,  # Updated type
):
```

#### 2. Add async-aware approval method

Add new method alongside existing `request_approval_sync`:

```python
async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
    """Async-aware approval request.

    Works with both sync and async callbacks. Checks mode and cache
    before invoking the callback.

    Args:
        request: The approval request

    Returns:
        ApprovalDecision with the result

    Raises:
        RuntimeError: If interactive mode has no callback
    """
    # Handle non-interactive modes
    if self.mode == "approve_all":
        return ApprovalDecision(approved=True)
    if self.mode == "strict":
        return ApprovalDecision(
            approved=False,
            note=f"Strict mode: {request.tool_name} requires approval"
        )

    # Check session cache
    cached = self._memory.lookup(request.tool_name, request.tool_args)
    if cached is not None:
        return cached

    # Prompt user
    if self._approval_callback is None:
        raise RuntimeError(
            "No approval_callback provided for interactive mode"
        )

    result = self._approval_callback(request)
    if inspect.isawaitable(result):
        decision = await result
    else:
        decision = result

    # Cache if remember="session"
    if decision.approved and decision.remember == "session":
        self._memory.store(request.tool_name, request.tool_args, decision)

    return decision
```

#### 3. Update `approval_callback` property return type

```python
@property
def approval_callback(self) -> ApprovalCallback:
    """Get the approval callback based on mode."""
    # ... existing implementation unchanged
```

### Import Changes

Add `import inspect` to both `toolset.py` and `controller.py`.

## Test Plan

### Unit Tests

1. **Sync callback still works** - Existing tests should pass unchanged
2. **Async callback works** - New test with `async def` callback
3. **Mixed nested calls** - Outer sync, inner async (and vice versa)
4. **Memory caching with async** - Session approvals cached correctly
5. **Controller modes with async** - `approve_all`/`strict` bypass async callback

### Integration Tests

1. **Nested tool approval (async)** - Tool A calls Tool B, both need approval
2. **Timeout handling** - Async callback that times out (user responsibility)
3. **Cancellation** - Async callback cancelled mid-flight

### Example Test Case

```python
import asyncio
import pytest
from pydantic_ai_blocking_approval import (
    ApprovalController,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
)

@pytest.mark.asyncio
async def test_async_callback():
    """Async callback is awaited correctly."""
    approvals = []

    async def async_callback(request: ApprovalRequest) -> ApprovalDecision:
        await asyncio.sleep(0.01)  # Simulate network delay
        approvals.append(request.tool_name)
        return ApprovalDecision(approved=True)

    controller = ApprovalController(
        mode="interactive",
        approval_callback=async_callback
    )

    # ... test toolset with controller

    assert "my_tool" in approvals
```

## Migration Guide

No migration required. Existing code continues to work:

```python
# Before and after - identical, still works:
def my_sync_callback(request: ApprovalRequest) -> ApprovalDecision:
    response = input(f"Approve {request.tool_name}? [y/n]: ")
    return ApprovalDecision(approved=response.lower() == "y")

controller = ApprovalController(
    mode="interactive",
    approval_callback=my_sync_callback
)
```

New async usage:

```python
# New capability:
async def my_async_callback(request: ApprovalRequest) -> ApprovalDecision:
    request_id = await message_queue.publish(request.model_dump())
    response = await message_queue.await_response(request_id, timeout=300)
    return ApprovalDecision(**response)

controller = ApprovalController(
    mode="interactive",
    approval_callback=my_async_callback
)
```

## Files Changed

| File | Changes |
|------|---------|
| `types.py` | Add `ApprovalCallback` type alias |
| `toolset.py` | `_prompt_for_approval` → async, await in `call_tool` |
| `controller.py` | Add `request_approval` async method, update type hints |
| `__init__.py` | Export `ApprovalCallback` |
| `tests/test_async_callback.py` | New test file |

## Open Questions

1. **Timeout support?** - Should the library provide timeout wrapper, or leave to user?
   - Recommendation: Leave to user (wrap their callback with `asyncio.timeout`)

2. **Cancellation semantics?** - What happens if async callback is cancelled?
   - Recommendation: Let `CancelledError` propagate (standard asyncio behavior)

3. **Deprecate `request_approval_sync`?** - Keep both or consolidate?
   - Recommendation: Keep both for now, `request_approval` is the preferred method
