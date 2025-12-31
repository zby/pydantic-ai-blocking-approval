# Design

## The Problem Space

At first glance, tool approval seems simple: ask "yes or no?" But real-world use cases reveal complexity:

1. **Different tools need different treatment** — `ls` is safe, `rm -rf` is dangerous
2. **Context matters** — `cat /tmp/log.txt` is fine, `cat /etc/shadow` is not
3. **Repetition is annoying** — approving the same operation 50 times kills productivity
4. **Environments differ** — CLI needs prompts, CI needs auto-deny, tests need auto-approve
5. **Async UIs exist** — web dashboards and Slack bots can't block synchronously

## Key Design Decisions

### 1. `ApprovalResult` with three explicit states

Instead of overloaded `bool | dict`, we use structured states:
- `ApprovalResult.blocked(reason)` — forbidden by policy
- `ApprovalResult.pre_approved()` — no prompt needed
- `ApprovalResult.needs_approval()` — requires user approval

Description generation is separate (`SupportsApprovalDescription` protocol), called only when approval is needed.

### 1.5 `ApprovalDecision` is structured (bool is not enough)

The approval callback returns `ApprovalDecision` because a bare boolean
cannot carry context back to the LLM/operator. `note` lets denials (or approvals)
explain why, and `remember` can signal caller-managed session caching.

### 2. Unified wrapper with protocol detection

A single `ApprovalToolset` auto-detects capabilities:
- Inner implements `SupportsNeedsApproval` → delegate to `inner.needs_approval(..., config)`
- Otherwise → use config dict for pre-approved tools via `needs_approval_from_config()`

Simple case uses config; complex case (e.g., shell command analysis) implements the protocol.
Custom toolsets can call `needs_approval_from_config(name, config)` to apply the
default policy before adding their own rules.

### 3. Secure by default

Tools require approval unless explicitly pre-approved. Forgetting to add a safe tool = minor inconvenience. Forgetting to restrict a dangerous tool = no security breach.

### 4. Callback patterns (optional controller)

Environment-specific behavior can be encoded directly in the callback:
- Approve-all: return `ApprovalDecision(approved=True)`
- Strict deny: return `ApprovalDecision(approved=False, note="Strict mode")`

### 5. Session caching

Approving 100 similar operations one-by-one is tedious. This package does not
implement caching; if you want it, wrap your callback to store decisions keyed
on `(tool_name, tool_args)` (or a canonicalized variant).

### 6. Sync and async callbacks

CLI tools use sync callbacks that block until user input. Web UIs and Slack bots need async callbacks that can await remote responses.

The library supports both:
```python
# Sync (CLI)
def cli_callback(request: ApprovalRequest) -> ApprovalDecision:
    response = input(f"Approve {request.tool_name}? [y/n]: ")
    return ApprovalDecision(approved=response == "y")

# Async (Web UI)
async def web_callback(request: ApprovalRequest) -> ApprovalDecision:
    approval_id = await send_to_dashboard(request)
    return await wait_for_response(approval_id)
```

Detection uses `inspect.isawaitable()` on the callback result, so any awaitable works.

### 7. Presentation is the CLI's responsibility

The library provides `tool_name`, `tool_args`, and `description`. The CLI decides how to render (diffs, syntax highlighting, truncation).

### 8. Exceptions for denied/blocked tools

When a tool is denied or blocked, `ApprovalToolset` raises an exception (`ApprovalDenied` or `ApprovalBlocked`) rather than returning an error value. This design choice keeps the wrapped tool unaware of the approval mechanism:

- `ApprovalToolset` acts as a wrapper that intercepts `call_tool()`
- It handles user interaction and only proceeds to the actual tool if approval is granted
- If denied, an exception provides a clean, Pythonic non-local exit from the wrapper
- The inner tool's code remains unchanged—no approval-related conditionals or return types

This separation means you can wrap any existing toolset without modifying it.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / UI Layer                       │
│  • Rendering, keyboard/mouse input                          │
│  • Provides sync or async approval_callback                 │
│  • Implements user prompting and mode behavior             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ApprovalToolset                         │
│  • Wraps any AbstractToolset                                │
│  • Auto-detects SupportsNeedsApproval protocol              │
│  • Handles ApprovalResult states                            │
│  • Calls callback, handles decision                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Inner Toolset                            │
│  • Implements actual tool logic                             │
│  • Optionally implements SupportsNeedsApproval              │
│  • Optionally implements SupportsApprovalDescription        │
└─────────────────────────────────────────────────────────────┘
```

Session caching belongs at the caller layer so hosts can define the keying and
scope rules that make sense for their app.

## Incremental Adoption

Start simple, add complexity as needed:

1. **Basic**: `ApprovalToolset` + config dict for pre-approved tools
2. **Custom logic**: Inner toolset implements `SupportsNeedsApproval`
3. **Custom descriptions**: Add `SupportsApprovalDescription`
4. **Callbacks**: Encode approve-all/strict behavior in the callback
5. **Async UI**: Switch to async callback
