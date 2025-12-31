# pydantic-ai-blocking-approval

Synchronous, blocking approval system for PydanticAI agent tools.

> **Status**: This package is experimental. The core wrapper (`ApprovalToolset`) is more mature, while pattern-based approval via `needs_approval()` is highly experimental and likely to change. See [design motivation](docs/notes/design_motivation.md) for details.

## Why This Package?

PydanticAI provides `DeferredToolRequests` for human-in-the-loop approval, following PydanticAI's core design philosophy of **stateless, functional tools**. This package provides an alternative for **synchronous, blocking** approval—a pattern that deliberately trades functional purity for interactive convenience.

### The Design Philosophy Tension

PydanticAI is built around stateless, reusable agents. Tools are pure functions. The deferred pattern preserves this:

```
Agent Run → Returns immediately with pending tools → [State serialized] → User approves later → New agent run resumes
```

This keeps tools stateless—they don't block waiting for I/O. Control flow returns to your application, which handles approval however it wants (webhooks, admin dashboards, Slack buttons).

**This package breaks that model.** Blocking approval pauses execution mid-tool-call:

```
Agent Run → Tool needs approval → [Blocks on user input] → User decides → Execution continues
```

The tool is no longer a pure function—it has a side effect (waiting for human input) that couples it to the runtime environment. This is an intentional trade-off.

### When Blocking Makes Sense

The deferred pattern struggles with two common patterns:

**1. Exploratory, multi-step tasks** where each step depends on the previous result:

```
You: "Find and kill the process hogging port 8080"

With deferred approval:
  Agent returns: pending shell_exec("lsof -i :8080")  ← needs approval
  Agent run ends here.

  You approve... but the agent already returned. It can't see the output
  (PID 1234 = node). You need a new conversation to continue.
```

The problem: the dangerous action (shell access) produces information the LLM needs to plan the next step. With deferred, each approval breaks the conversation.

```
With blocking approval:
  Agent: I'll find what's using port 8080.
  [APPROVAL REQUIRED] shell_exec("lsof -i :8080") [y/n]: y
  Output: node (PID 1234)

  Agent: Found it - node process 1234. I'll kill it.
  [APPROVAL REQUIRED] shell_exec("kill 1234") [y/n]: y

  Done! Port 8080 is free.
```

Blocking keeps the LLM "in the loop"—it sees each result and plans accordingly.

**2. Recursive/nested tool calls** where tools spawn sub-agents or delegate work:

```python
# A "call_worker" tool that delegates focused tasks to a sub-agent
@agent.tool
def call_worker(ctx: RunContext, task: str) -> str:
    """Spawn a focused worker agent for a specific subtask."""
    worker_result = worker_agent.run_sync(task)  # ← This needs to actually execute
    return worker_result.output
```

With deferred approval, `call_worker` can't actually call anything—it returns immediately with a pending state. The recursive invocation never happens. You'd need to:
1. Approve the outer `call_worker` call
2. Resume... but now the worker's tools need approval
3. Approve each worker tool, one agent run at a time
4. Somehow stitch the results back together

The hierarchical context is lost. With blocking, the entire call tree executes naturally, with approval prompts appearing inline as needed.

### Comparison

| Aspect | Deferred (PydanticAI) | Blocking (this package) |
|--------|----------------------|-------------------------|
| **Philosophy** | Stateless tools, functional purity | Trades purity for interactivity |
| **Execution** | Agent run returns, resumes later | Agent pauses mid-execution |
| **Timing** | Minutes to days | Immediate |
| **Multi-step tasks** | Each approval breaks the flow | Continuous conversation |
| **State management** | You serialize/persist pending state | None needed |
| **Best for** | Web apps, APIs, async workflows | CLI tools, interactive sessions |

### When to Use Which

**Use PydanticAI's deferred tools when:**
- User isn't present during execution
- Approval can happen out-of-band (email, dashboard, Slack)
- Tasks are self-contained (approval doesn't affect planning)
- You need the stateless/functional model

**Use blocking approval when:**
- User is at the terminal, watching execution
- Tasks are exploratory (each step informs the next)
- You want "approve and continue" without conversation breaks
- Simplicity matters more than functional purity

### Honest Trade-offs

This package intentionally breaks PydanticAI's design principles. You should understand the costs:

**What you lose with blocking:**
- **Stateless tools** — Your approval callback has side effects (user I/O)
- **Testability** — Can't run agent without mocking the callback
- **Scalability** — One blocked agent = one blocked event loop slot
- **Async purity** — You're mixing sync blocking into async code

**What you gain:**
- **Continuous conversation** — LLM sees each result, plans next step
- **Simple mental model** — Approve and continue, no state to manage
- **Interactive UX** — Real-time approval at the terminal

**If PydanticAI adds blocking approval natively**, you should probably use that instead. This package exists because the deferred pattern doesn't work well for CLI tools with exploratory, multi-step tasks—a gap that may be filled upstream.

## Architecture Overview

```
ApprovalToolset (unified wrapper)
    ├── intercepts call_tool()
    ├── auto-detects if inner implements SupportsNeedsApproval
    │   ├── YES: delegates to inner.needs_approval(..., config) → ApprovalResult
    │   └── NO: uses needs_approval_from_config(name, config)
    ├── handles ApprovalResult:
    │   ├── blocked → raises PermissionError
    │   ├── pre_approved → proceeds without prompting
    │   └── needs_approval → prompts user
    ├── calls approval_callback and BLOCKS until user decides
    └── proceeds or raises PermissionError
```

**How it works:** `ApprovalToolset` automatically detects whether your inner toolset implements the `SupportsNeedsApproval` protocol. If it does, approval decisions are delegated to `inner.needs_approval(..., config)` which returns an `ApprovalResult` (blocked, pre_approved, or needs_approval). Otherwise, it falls back to config-based approval (secure by default) using `needs_approval_from_config()`.

**Note on async:** The toolset methods are `async` because PydanticAI's `AbstractToolset` interface requires it. The "blocking" refers to the `approval_callback` — a synchronous function that blocks the coroutine until the user decides. `needs_approval()` may be sync or async; if it returns an awaitable, `ApprovalToolset` awaits it. So `async def call_tool()` awaits the inner toolset, but the approval prompt in the middle is synchronous and blocking.

## Installation

```bash
pip install pydantic-ai-blocking-approval
```

## Quick Start

```python
from pydantic_ai import Agent
from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
)

# Create a callback for interactive approval
def my_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
    print(f"Approve {request.tool_name}? {request.description}")
    response = input("[y/n]: ")
    return ApprovalDecision(approved=response.lower() == "y")

# Wrap your toolset with approval using per-tool config
approved_toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=my_approval_callback,
    config={
        "safe_tool": {"pre_approved": True},
        # All other tools require approval (secure by default)
    },
)

# Use with PydanticAI agent
agent = Agent(..., toolsets=[approved_toolset])
```

## Callback Returns ApprovalDecision

The approval callback returns an `ApprovalDecision`, which includes:
- `approved`: allow/deny
- `note`: optional reason for the LLM/user
- `remember`: optional hint for caller-managed session caching

Returning a bare `bool` is rejected. Denied calls raise `ApprovalDenied` (with the `ApprovalDecision` attached), and policy blocks raise `ApprovalBlocked`.

Session caching, approval scopes ("approve all file reads"), undo/redo, audit logging—these all require state management that varies wildly by use case:

- CLI tools might cache approvals in memory for the session
- Web apps might persist them in a database with user scopes
- Slack bots might track approvals per channel or thread
- Desktop apps might integrate with OS keychain

There's no universal abstraction for "session" or "scope" that works across these contexts. Rather than provide a leaky abstraction, this package gives you a minimal decision type (`ApprovalDecision`) and lets you build the state management that fits your domain.

### Example Patterns

```python
# Auto-approve everything (tests/CI)
def approve_all(_: ApprovalRequest) -> ApprovalDecision:
    return ApprovalDecision(approved=True)

# Auto-deny everything (strict safety)
def deny_all(_: ApprovalRequest) -> ApprovalDecision:
    return ApprovalDecision(approved=False, note="Strict mode")
```

## Integration Patterns

### Pattern 1: Config-Based (Simple Inner Toolsets)

For simple inner toolsets, specify which tools skip approval via the `config` parameter:

```python
approved_toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=my_approval_callback,
    config={
        "get_time": {"pre_approved": True},
        "list_files": {"pre_approved": True},
        "get_weather": {"pre_approved": True},
        # All other tools require approval (secure by default)
    },
)
```

Tools with `pre_approved: True` skip approval. Tools not in config require approval by default (secure by default).

### Pattern 2: Protocol-Based (Smart Inner Toolsets)

For inner toolsets with custom approval logic, implement `SupportsNeedsApproval`:

```python
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai_blocking_approval import (
    ApprovalResult,
    ApprovalToolset,
    needs_approval_from_config,
)

class MySmartToolset(AbstractToolset):
    """Inner toolset with custom approval logic (implements SupportsNeedsApproval)."""

    SAFE_COMMANDS = {"ls", "pwd", "echo", "date"}
    BLOCKED_COMMANDS = {"rm -rf /", "shutdown"}

    def needs_approval(
        self,
        name: str,
        tool_args: dict,
        ctx: RunContext,
        config: dict[str, dict[str, Any]],
    ) -> ApprovalResult:
        base = needs_approval_from_config(name, config)
        if base.is_pre_approved:
            return base
        if name == "safe_tool":
            return ApprovalResult.pre_approved()

        # Custom logic for shell_exec
        if name == "shell_exec":
            command = tool_args.get("command", "")
            base_cmd = command.split()[0] if command else ""

            # Block dangerous commands entirely
            if command in self.BLOCKED_COMMANDS:
                return ApprovalResult.blocked(f"Command '{command}' is forbidden")

            if base_cmd in self.SAFE_COMMANDS:
                return ApprovalResult.pre_approved()

            return ApprovalResult.needs_approval()

        # Can also use ctx.deps for user-specific approval logic
        return ApprovalResult.needs_approval()

    def get_approval_description(self, name: str, tool_args: dict, ctx: RunContext) -> str:
        """Return human-readable description for approval prompt."""
        if name == "shell_exec":
            return f"Execute: {tool_args.get('command', '')}"
        return f"{name}({tool_args})"

    # ... other toolset methods ...

# ApprovalToolset auto-detects needs_approval and delegates to it
approved = ApprovalToolset(
    inner=MySmartToolset(),
    approval_callback=my_callback,
)
```

## Session Approval Caching (Caller-Side)

Session caching is intentionally not built into this package. If you want
approve-for-session behavior, implement it in your callback wrapper:

```python
import json

from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
)

def prompt_user(request: ApprovalRequest) -> str:
    return input(
        f"Approve {request.tool_name}? [y]es / [n]o / [s]ession: "
    ).strip().lower()

def with_session_cache(prompt):
    cache = {}

    def wrapper(request: ApprovalRequest) -> ApprovalDecision:
        key = (
            request.tool_name,
            json.dumps(request.tool_args, sort_keys=True, default=str),
        )
        cached = cache.get(key)
        if cached is not None:
            return cached

        response = prompt(request)
        if response == "s":
            decision = ApprovalDecision(approved=True, remember="session")
        elif response == "y":
            decision = ApprovalDecision(approved=True)
        else:
            decision = ApprovalDecision(approved=False, note="User denied")

        if decision.approved and decision.remember == "session":
            cache[key] = decision
        return decision

    return wrapper

approved_toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=with_session_cache(prompt_user),
)
```

Choose a keying strategy that matches your domain (e.g., stable JSON, hashing,
or custom serializers for non-JSON tool args).

## API Reference

### Types

- `ApprovalResult` - Structured result from approval checking (blocked/pre_approved/needs_approval)
- `ApprovalRequest` - Request object when approval is needed
- `ApprovalDecision` - User's decision (approved, note, remember)
- `ApprovalCallback` - Approval callback signature (sync/async decision)
- `SupportsNeedsApproval` - Protocol for toolsets with custom approval logic
- `SupportsApprovalDescription` - Protocol for custom approval descriptions

### Exceptions

- `ApprovalError` - Base exception for approval failures (subclasses `PermissionError`)
- `ApprovalDenied` - Raised when a user denies a tool call (contains `decision`)
- `ApprovalBlocked` - Raised when a tool call is blocked by policy (contains `reason`)

### Classes

- `ApprovalToolset` - Unified wrapper (auto-detects inner toolset capabilities)

## License

MIT
