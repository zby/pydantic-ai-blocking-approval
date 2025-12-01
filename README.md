# pydantic-ai-blocking-approval

Synchronous, blocking approval system for PydanticAI agent tools.

> **Status**: This package is experimental. The core wrapper (`ApprovalToolset`, `ApprovalController`) is more mature, while pattern-based approval via `needs_approval()` is highly experimental and likely to change. See [design motivation](docs/notes/design_motivation.md) for details.

## Why This Package?

PydanticAI provides `DeferredToolRequests` for human-in-the-loop approval, but it's designed for **asynchronous, out-of-band** approval flows. This package provides an alternative for **synchronous, blocking** approval - a fundamentally different pattern.

### PydanticAI's Deferred Tools (async/out-of-band)

```
Agent Run → Returns with pending tools → [Time passes] → User approves via API/webhook → Resume agent
```

The deferred pattern is ideal when:
- User isn't present during execution (web apps, background jobs)
- Approval happens out-of-band (email links, admin dashboards, Slack buttons)
- Hours or days may pass between request and approval
- You need to serialize/persist the pending state

### Blocking Approval (this package)

```
Agent Run → Tool needs approval → [Blocks] → User prompted immediately → [Decides] → Execution continues
```

The blocking pattern is ideal when:
- User is present at the terminal (CLI tools, interactive sessions)
- Approval must happen immediately, inline with execution
- The agent run should complete in one continuous session
- You want simple "approve and continue" UX without state management

### Comparison

| Aspect | Deferred (PydanticAI) | Blocking (this package) |
|--------|----------------------|-------------------------|
| **Execution** | Agent run completes, returns pending | Agent run pauses mid-execution |
| **Timing** | Minutes to days between request/approval | Immediate, synchronous |
| **User presence** | Not required during execution | Must be present |
| **State** | Must serialize/persist pending state | No state management needed |
| **Resume** | Explicit resume call with decisions | Automatic after user input |
| **Best for** | Web apps, APIs, async workflows | CLI tools, interactive sessions |

### Why Blocking Matters for Dangerous Actions

Consider: you ask the agent to "find and kill the process hogging port 8080."

**With deferred approval:**
```
Agent run completes with pending actions:
  1. shell_exec("lsof -i :8080")    ← Needs approval (shell access)

Agent run ends here - LLM can't plan further because it doesn't
know what process is using the port until the command runs.

You approve... command shows PID 1234 (node). But the agent didn't
plan the kill command. You need a new conversation to continue.
```

The problem: the dangerous action (shell access) produces information the LLM needs to plan the next step. With deferred approval, it can't proceed.

**With blocking approval:**
```
Agent: I'll find what's using port 8080.

[APPROVAL REQUIRED] shell_exec("lsof -i :8080")
[y/n/s]: y

Output: node (PID 1234)

Agent: Found it - node process 1234. I'll kill it.

[APPROVAL REQUIRED] shell_exec("kill 1234")
[y/n/s]: y

Done! Process killed, port 8080 is now free.
```

The key difference: with blocking, the LLM sees the result of each approved action and plans accordingly. With deferred, dangerous actions that produce information block all further progress.

## Architecture Overview

```
ApprovalToolset (wraps any toolset)
    ├── intercepts call_tool()
    ├── calls needs_approval(name, tool_args) — override for custom logic
    ├── default: checks config[tool_name]["pre_approved"]
    ├── consults ApprovalMemory for cached decisions
    ├── calls approval_callback and BLOCKS until user decides
    └── proceeds or raises PermissionError

ApprovalController (manages modes)
    ├── interactive — prompts user via callback
    ├── approve_all — auto-approve (testing)
    └── strict — auto-deny (safety)
```

**Secure by default**: Tools not configured with `pre_approved: True` require approval. This ensures forgotten tools prompt rather than silently execute.

## Installation

```bash
pip install pydantic-ai-blocking-approval
```

## Quick Start

```python
from pydantic_ai import Agent
from pydantic_ai_blocking_approval import (
    ApprovalController,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
)

# Create a callback for interactive approval
def my_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
    print(f"Approve {request.tool_name}? {request.description}")
    response = input("[y/n/s(ession)]: ")
    if response == "s":
        return ApprovalDecision(approved=True, remember="session")
    return ApprovalDecision(approved=response.lower() == "y")

# Wrap your toolset with approval using per-tool config
controller = ApprovalController(mode="interactive", approval_callback=my_approval_callback)
approved_toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=controller.approval_callback,
    memory=controller.memory,
    config={
        "safe_tool": {"pre_approved": True},
        # All other tools require approval (secure by default)
    },
)

# Use with PydanticAI agent
agent = Agent(..., toolsets=[approved_toolset])
```

## Approval Modes

The `ApprovalController` supports three modes:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `interactive` | Prompts user via callback | CLI with user present |
| `approve_all` | Auto-approves all requests | Testing, CI |
| `strict` | Auto-denies all requests | Production safety |

```python
# For testing - auto-approve everything
controller = ApprovalController(mode="approve_all")

# For CI/production - reject all approval-required operations
controller = ApprovalController(mode="strict")
```

## Integration Patterns

### Pattern 1: Config-Based Pre-Approval

Specify which tools skip approval via the `config` parameter:

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

### Pattern 2: Custom Approval Logic via Subclass

For complex tools (like file sandboxes or shell executors), subclass `ApprovalToolset` and override `needs_approval()`:

```python
class ShellApprovalToolset(ApprovalToolset):
    """Shell command approval with pattern matching."""

    SAFE_COMMANDS = {"ls", "pwd", "echo", "date"}

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        # Check pre_approved config first
        tool_config = self.config.get(name, {})
        if tool_config.get("pre_approved"):
            return False

        # Custom logic for shell_exec
        if name == "shell_exec":
            command = tool_args.get("command", "")
            base_cmd = command.split()[0] if command else ""

            if base_cmd in self.SAFE_COMMANDS:
                return False  # Safe command

            return {"description": f"Execute: {command}"}

        return True  # Default: require approval

# Usage
toolset = ShellApprovalToolset(
    inner=shell_toolset,
    approval_callback=callback,
    config={
        "get_cwd": {"pre_approved": True},  # Additional pre-approved tools
    },
)
```

See `tests/test_integration.py` for a complete example with pattern matching for safe commands and dangerous patterns.

## Session Approval Caching

When users approve with `remember="session"`, subsequent identical requests are auto-approved:

```python
# First call - prompts user
# User selects "approve for session"
decision = ApprovalDecision(approved=True, remember="session")

# Subsequent identical calls - auto-approved from cache
# (same tool_name + tool_args)
```

The cache key is `(tool_name, tool_args)`.

## API Reference

### Types

- `ApprovalRequest` - Request object when approval is needed
- `ApprovalDecision` - User's decision (approved, note, remember)

### Classes

- `ApprovalMemory` - Session cache for "approve for session"
- `ApprovalToolset` - Wrapper that intercepts tool calls (subclass for custom logic)
- `ApprovalController` - Mode-based controller

## License

MIT
