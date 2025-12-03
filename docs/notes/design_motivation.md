# Design Motivation — Why This Complexity?

> This document explains the reasoning behind the `pydantic-ai-blocking-approval` architecture. If you're wondering "why not just a simple approve/deny function?", read on.

---

## ⚠️ Status Notice

This package is experimental. All APIs may change.

**Core components:**
- `ApprovalToolset` unified wrapper (auto-detects inner toolset capabilities)
- `SupportsNeedsApproval` protocol for custom approval logic
- `ApprovalController` with modes (interactive/approve_all/strict)
- `ApprovalMemory` for session caching
- `ApprovalDecision` with `remember="session"`

---

## The Problem Space

At first glance, tool approval seems simple: before a tool runs, ask the user "yes or no?" But real-world use cases quickly reveal layers of complexity:

1. **Different tools need different treatment** — `ls` is safe, `rm -rf` is dangerous
2. **Context matters** — `cat /tmp/log.txt` is fine, `cat /etc/shadow` is not
3. **Repetition is annoying** — approving the same safe operation 50 times kills productivity
4. **Environments differ** — interactive CLI needs prompts, CI needs auto-deny, tests need auto-approve
5. **Presentation matters** — a file diff is more useful than raw JSON args

The architecture addresses each of these concerns through layered abstractions.

---

## Design Decisions Explained

### 1. Why `needs_approval()` returns `bool | dict`?

**Single-return-type alternative**: Two separate methods (`needs_approval() -> bool` and `present_for_approval() -> dict`).

**Problem**: Duplicate computation. A shell toolset checking if `rm -rf /` is dangerous would:
1. Parse the command in `needs_approval()` to return `True`
2. Parse it again in `present_for_approval()` to build the warning message

**Solution**: One method that returns:
- `False` — no approval needed
- `True` — approval needed, use default presentation
- `dict` — approval needed, here's the custom presentation I already computed

This eliminates the coupling and lets the toolset make one decision with all the context.

### 2. Why a unified wrapper with protocol detection?

**Previous design**: Two separate wrapper classes (`SimpleApprovalToolset` for config-based, `ApprovalToolset` for delegating).

**Problem**: Users had to choose the right wrapper, and the distinction was confusing.

**Solution**: A single `ApprovalToolset` that auto-detects capabilities:
- If inner implements `SupportsNeedsApproval` protocol → delegate to `inner.needs_approval()`
- Otherwise → use config dict for `pre_approved` settings

**Simple case**: A basic toolset with a few safe read-only tools uses config:
```python
ApprovalToolset(
    inner=my_toolset,
    approval_callback=callback,
    config={
        "get_time": {"pre_approved": True},
        "list_files": {"pre_approved": True},
    },
)
```

**Complex case**: A shell executor needs to analyze each command. The inner toolset implements the `SupportsNeedsApproval` protocol:
```python
class ShellToolset(AbstractToolset):
    def needs_approval(self, name, tool_args):
        command = tool_args.get("command", "")
        if command.startswith("ls "):
            return False  # Safe
        if "rm " in command:
            return {"description": f"Delete: {command}"}  # Dangerous
        return True

    # ... tool implementations ...

# ApprovalToolset auto-detects needs_approval and delegates to it
ApprovalToolset(inner=ShellToolset(), approval_callback=callback)
```

This keeps approval logic with the toolset that understands its domain, while providing a simple config-based fallback for toolsets that don't need custom logic.

### 3. Why "secure by default" (unlisted tools require approval)?

**Alternative**: "open by default" where only listed tools require approval.

**Problem**: Forgetting to add a dangerous tool to the list = security hole.

**Solution**: Flip the logic. Tools require approval unless explicitly pre-approved. Forgetting to add a safe tool = minor inconvenience (extra prompts). Forgetting to restrict a dangerous tool = no security breach.

This follows the principle of least privilege.

### 4. Why is presentation the CLI's responsibility?

**Alternative**: The package could include a structured `ApprovalPresentation` type with `type`, `content`, `language` fields.

**Problem**: This creates unnecessary coupling. The CLI already knows the tool name from `ApprovalRequest.tool_name` and can maintain its own mapping for how to render each tool's arguments.

**Solution**: Keep `ApprovalRequest` simple with just `tool_name`, `tool_args`, and `description`. The CLI can:
- Look up rendering logic by tool name
- Parse the tool_args to extract display-relevant data
- Render appropriately (diff for patches, syntax highlight for code, etc.)

This follows separation of concerns: the package handles approval flow, the CLI handles presentation.

### 5. Why `ApprovalController` with modes?

Different environments need different behaviors:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `interactive` | Prompt user | CLI with operator present |
| `approve_all` | Auto-approve | Unit tests, trusted dev |
| `strict` | Auto-deny | CI pipelines, production |

**Without modes**: Every test would need mock callbacks. Production code would need TTY detection.

**With modes**:
```python
# Test
controller = ApprovalController(mode="approve_all")

# Production
controller = ApprovalController(mode="strict")

# Interactive
controller = ApprovalController(mode="interactive", approval_callback=cli_prompt)
```

The same toolset works in all environments by swapping the controller.

### 6. Why session caching with `remember="session"`?

**Scenario**: Agent deletes 100 old log files. Without caching:
```
Approve rm /tmp/log1.txt? [y/n] y
Approve rm /tmp/log2.txt? [y/n] y
... (98 more times)
```

**With session caching**:
```
Approve rm /tmp/log1.txt? [y/n/s] s  # 's' = session
(remaining 99 auto-approved)
```

The cache key is `(tool_name, tool_args)`, so:
- Same command → uses cache
- Different command → prompts again

Session approvals reset when the run ends — they don't persist across runs.

---

## User Story Coverage

This architecture supports the [CLI Approval User Stories](cli_approval_user_stories.md):

| Story | Status | Implementation |
|-------|--------|----------------|
| 1. Pause on guarded tool | ✅ | `approval_callback` blocks until decision |
| 2. Approve and resume | ✅ | Approval unblocks, execution continues |
| 3. Reject with feedback | ✅ | `ApprovalDecision(approved=False, note="...")` |
| 4. Pre-approve in config | ✅ | `config` dict with `pre_approved: True` |
| 5. Approve for session | ✅ | `remember="session"` + `ApprovalMemory` |
| 6. Auto-approve all | ✅ | `ApprovalController(mode="approve_all")` |
| 7. Strict mode | ✅ | `ApprovalController(mode="strict")` |
| 8. Shell command approval | ✅ | Any tool can require approval |
| 9. Pattern-based pre-approval | ✅ | Inner toolset implements `needs_approval()` |
| 10. Block dangerous commands | ✅ | `needs_approval()` returns `True`, callback denies, raises `PermissionError` |
| 11-13. Worker/delegation approval | ✅ | Generic — any tool type works |
| 14. See approval history | ✅ | `ApprovalMemory.list_approvals()` |
| 15-18. Rich presentation | ⚠️ | CLI responsibility (see note below) |

**Note on Stories 15-18 (Rich Presentation):**

These stories require the **CLI** to implement presentation logic. This library provides:
- `tool_name` — to determine presentation type (e.g., "patch_file", "write_file", "shell")
- `tool_args` — raw data to render (e.g., file path, content, command)
- `description` — human-readable summary

The CLI must implement:
- **Diff rendering** (Story 15): Render `tool_args["diff"]` for `patch_file` operations
- **Flexible file presentation** (Story 16): For `write_file`, decide based on context:
  - Small files: show full content with syntax highlighting
  - Large files: show summary (line count, size) with view option
  - Overwrites: optionally compute diff against existing file
- **Shell formatting** (Story 17): Format `tool_args["command"]` with `$` prefix
- **Truncation/paging** (Story 18): Based on content length in `tool_args`

This separation keeps the approval library simple and decoupled from UI concerns.

---

## The Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│  • TTY detection (Story 15)                                 │
│  • Rich rendering based on tool_name + tool_args            │
│  • Keyboard input handling                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   ApprovalController                        │
│  • Mode selection (interactive/approve_all/strict)          │
│  • Provides approval_callback based on mode                 │
│  • Owns ApprovalMemory for session caching                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                ApprovalToolset (unified)                    │
│  • Wraps any AbstractToolset                                │
│  • Auto-detects SupportsNeedsApproval protocol              │
│    ├── YES: delegates to inner.needs_approval()             │
│    └── NO: uses config[name]["pre_approved"]                │
│  • Builds ApprovalRequest with description                  │
│  • Consults cache, calls approval_callback, handles decision│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Inner Toolset                            │
│  • Implements actual tool logic                             │
│  • Optionally implements SupportsNeedsApproval protocol     │
│    for custom approval logic                                │
└─────────────────────────────────────────────────────────────┘
```

Each layer has a single responsibility:
- **CLI**: User interaction and display
- **Controller**: Mode-based behavior and session memory
- **ApprovalToolset**: Approval flow orchestration (auto-detects inner capabilities)
- **Inner Toolset**: Domain logic (and optionally approval logic via `SupportsNeedsApproval`)

---

## When is This Complexity Warranted?

**Use the full architecture when**:
- Building a CLI tool with human-in-the-loop approval
- Tools have varying risk levels (some safe, some dangerous)
- Users need session caching to avoid repetitive prompts
- You need different modes for dev/test/production

**Use a simpler approach when**:
- All tools are equally sensitive (just wrap everything)
- No session caching needed
- Single environment (no mode switching)

The architecture is designed to be adoptable incrementally — start with `ApprovalToolset` + config, implement `SupportsNeedsApproval` in your inner toolset when you need per-call decisions.
