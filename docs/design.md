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

### 2. Unified wrapper with protocol detection

A single `ApprovalToolset` auto-detects capabilities:
- Inner implements `SupportsNeedsApproval` → delegate to `inner.needs_approval()`
- Otherwise → use config dict for pre-approved tools

Simple case uses config; complex case (e.g., shell command analysis) implements the protocol.

### 3. Secure by default

Tools require approval unless explicitly pre-approved. Forgetting to add a safe tool = minor inconvenience. Forgetting to restrict a dangerous tool = no security breach.

### 4. Controller with modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `interactive` | Prompt user | CLI with operator present |
| `approve_all` | Auto-approve | Tests, trusted dev |
| `strict` | Auto-deny | CI, production |

### 5. Session caching

Approving 100 similar operations one-by-one is tedious. With `remember="session"`, the first approval covers subsequent identical calls. Cache key is `(tool_name, tool_args)`.

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

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / UI Layer                       │
│  • Rendering, keyboard/mouse input                          │
│  • Provides sync or async approval_callback                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   ApprovalController                        │
│  • Mode selection (interactive/approve_all/strict)          │
│  • Owns ApprovalMemory for session caching                  │
│  • request_approval() handles both sync/async callbacks     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ApprovalToolset                         │
│  • Wraps any AbstractToolset                                │
│  • Auto-detects SupportsNeedsApproval protocol              │
│  • Handles ApprovalResult states                            │
│  • Consults cache, calls callback, handles decision         │
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

## Incremental Adoption

Start simple, add complexity as needed:

1. **Basic**: `ApprovalToolset` + config dict for pre-approved tools
2. **Custom logic**: Inner toolset implements `SupportsNeedsApproval`
3. **Custom descriptions**: Add `SupportsApprovalDescription`
4. **Modes**: Use `ApprovalController` for environment-specific behavior
5. **Async UI**: Switch to async callback
