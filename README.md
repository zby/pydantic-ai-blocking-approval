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

### Rejection and LLM Adjustment

A key advantage of blocking approval is the **immediate feedback loop**. When a user rejects a tool call, the rejection (and optional note) is returned to the LLM, which can adjust its approach within the same conversation:

```python
def cli_prompt(request: ApprovalRequest) -> ApprovalDecision:
    print(f"Tool: {request.tool_name}")
    print(f"Args: {request.payload}")
    response = input("[y]es / [n]o: ")
    if response.lower() == "y":
        return ApprovalDecision(approved=True)
    # User provides feedback for the LLM to adjust
    reason = input("Why? ") or "User rejected"
    return ApprovalDecision(approved=False, note=reason)
```

**Example conversation flow:**

```
User: Delete the old log files

LLM: [calls delete_file(path="application.log")]
     → User rejects: "That's the current log, delete archived ones"

LLM: [calls delete_file(path="logs/archive/2024-01.log")]
     → User approves

LLM: [calls delete_file(path="logs/archive/2024-02.log")]
     → User approves for session

LLM: [remaining archive files auto-approved from session cache]
```

With **deferred approval**, the agent run terminates on rejection, requiring a new conversation to retry. With **blocking approval**, the LLM learns from rejection feedback and adjusts within the same run.

## Architecture Overview

```
ApprovalToolset (wraps any toolset)
    ├── intercepts call_tool()
    ├── checks pre_approved list (which tools skip approval)
    ├── calls needs_approval() if toolset implements it (per-call decision)
    ├── consults ApprovalMemory for cached decisions
    ├── calls prompt_fn and BLOCKS until user decides
    └── proceeds or raises PermissionError

ApprovalController (manages modes)
    ├── interactive — prompts user via callback
    ├── approve_all — auto-approve (testing)
    └── strict — auto-deny (safety)
```

**Secure by default**: Tools not in the `pre_approved` list require approval. This ensures forgotten tools prompt rather than silently execute.

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

# Create a prompt function for interactive approval
def cli_prompt(request: ApprovalRequest) -> ApprovalDecision:
    print(f"Approve {request.tool_name}? {request.description}")
    response = input("[y/n/s(ession)]: ")
    if response == "s":
        return ApprovalDecision(approved=True, remember="session")
    return ApprovalDecision(approved=response.lower() == "y")

# Wrap your toolset with approval
controller = ApprovalController(mode="interactive", approval_callback=cli_prompt)
approved_toolset = ApprovalToolset(
    inner=my_toolset,
    prompt_fn=controller.approval_callback,
    memory=controller.memory,
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

### Pattern 1: @requires_approval Decorator

Mark individual functions as requiring approval:

```python
from pydantic_ai_blocking_approval import requires_approval

@requires_approval
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email - requires user approval."""
    return f"Email sent to {to}"
```

### Pattern 2: pre_approved List

Specify which tools skip approval via the `pre_approved` parameter:

```python
approved_toolset = ApprovalToolset(
    inner=my_toolset,
    prompt_fn=cli_prompt,
    pre_approved=["get_time", "list_files", "get_weather"],
)
```

Tools in the list skip approval. Tools not in the list require approval by default (secure by default).

### Pattern 3: Custom Approval Logic (Highly Experimental)

> **Note**: This pattern is highly experimental and likely to change significantly as we build production toolsets.

For complex tools (like file sandboxes or shell executors), implement `needs_approval()` to decide per-call:

```python
class MyToolset:
    def needs_approval(self, tool_name: str, args: dict) -> bool | dict:
        """Decide if approval is needed and customize presentation.

        Returns:
            - False: no approval needed
            - True: approval needed with default presentation
            - dict: approval needed with custom presentation
        """
        if tool_name != "shell_exec":
            return False

        command = args["command"]
        if self._is_safe_command(command):
            return False

        # Dangerous command - require approval with custom presentation
        return {
            "description": f"Execute: {command[:50]}...",
            "payload": {"command": command},
        }
```

See `tests/test_integration.py` for a complete `ShellToolset` example with pattern matching.

## Session Approval Caching

When users approve with `remember="session"`, subsequent identical requests are auto-approved:

```python
# First call - prompts user
# User selects "approve for session"
decision = ApprovalDecision(approved=True, remember="session")

# Subsequent identical calls - auto-approved from cache
# (same tool_name + payload)
```

The cache key is `(tool_name, payload)`, so tools control matching granularity via their payload design.

## Rich Presentation (Highly Experimental)

> **Note**: This feature is highly experimental. The `ApprovalPresentation` structure will likely change.

Tools can provide enhanced UI hints via `ApprovalPresentation`:

```python
from pydantic_ai_blocking_approval import ApprovalPresentation, ApprovalRequest

request = ApprovalRequest(
    tool_name="write_file",
    description="Write to config.json",
    payload={"path": "config.json"},
    presentation=ApprovalPresentation(
        type="diff",
        content="- old value\n+ new value",
        language="json",
    ),
)
```

Supported presentation types:
- `text` - Plain text
- `diff` - Side-by-side diff
- `file_content` - Syntax-highlighted code
- `command` - Shell command
- `structured` - Tabular/tree data

## API Reference

### Types

- `ApprovalRequest` - Request object when approval is needed
- `ApprovalDecision` - User's decision (approved, note, remember)
- `ApprovalPresentation` - Rich UI hints for display

### Classes

- `ApprovalMemory` - Session cache for "approve for session"
- `ApprovalToolset` - Wrapper that intercepts tool calls
- `ApprovalController` - Mode-based controller

### Protocols

- `ApprovalConfigurable` - Protocol for toolsets with `needs_approval() -> bool | dict`

### Decorators

- `@requires_approval` - Mark functions as needing approval

## License

MIT
