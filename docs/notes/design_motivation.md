# Design Motivation — Why This Complexity?

> This document explains the reasoning behind the `pydantic-ai-blocking-approval` architecture. If you're wondering "why not just a simple approve/deny function?", read on.

---

## ⚠️ Status Notice

This package is experimental. All APIs may change.

**More mature:**
- `ApprovalToolset` wrapper with `pre_approved` list
- `ApprovalController` with modes (interactive/approve_all/strict)
- `ApprovalMemory` for session caching
- `ApprovalDecision` with `remember="session"`

**Highly experimental (likely to change significantly):**
- `needs_approval() -> bool | dict` protocol for complex pattern-based approval
- `ApprovalPresentation` structure for rich display hints
- Custom `payload` design for cache granularity control

The pattern-based approval examples (like `ShellToolset` in tests) demonstrate the *intended* design direction, but no production toolsets have been built yet. The `needs_approval()` API will likely evolve significantly as we learn from real implementations.

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

### 2. Why `pre_approved` list AND `needs_approval()` method?

These serve different use cases:

| Mechanism | Use Case | Example |
|-----------|----------|---------|
| `pre_approved` list | Simple static allowlist | `pre_approved=["get_time", "list_files"]` |
| `needs_approval()` | Dynamic per-call decisions | Shell command pattern matching |

**Simple case**: A basic toolset with a few safe read-only tools just uses `pre_approved`.

**Complex case**: A shell executor needs to analyze each command:
```python
def needs_approval(self, tool_name, args):
    command = args["command"]
    if command.startswith("ls "):
        return False  # Safe
    if "rm " in command:
        return {"description": f"Delete: {command}", ...}  # Dangerous
```

Without `pre_approved`, simple toolsets would need to implement `needs_approval()` just to return `False` for safe tools.

### 3. Why "secure by default" (unlisted tools require approval)?

**Alternative**: "open by default" where only listed tools require approval.

**Problem**: Forgetting to add a dangerous tool to the list = security hole.

**Solution**: Flip the logic. Tools require approval unless explicitly pre-approved. Forgetting to add a safe tool = minor inconvenience (extra prompts). Forgetting to restrict a dangerous tool = no security breach.

This follows the principle of least privilege.

### 4. Why separate `payload` from `tool_args`?

The `payload` in `ApprovalRequest` controls session cache matching:

```python
# Tool args might include timestamps, request IDs, etc.
tool_args = {"command": "rm /tmp/file.txt", "timestamp": 1234567890}

# But for caching, we only care about the command
payload = {"command": "rm /tmp/file.txt"}
```

**Without separation**: Session approval for `rm /tmp/file.txt` at timestamp X wouldn't match the same command at timestamp Y.

**With separation**: Toolset controls cache granularity via `payload`. Same command = same cache key, regardless of metadata.

### 5. Why `ApprovalPresentation` as a structured type?

**Alternative**: Just pass the args as JSON to the prompt.

**Problem**: A file write shows `{"path": "config.json", "content": "{\n  \"debug\": true\n}"}` — hard to read.

**Solution**: Structured presentation hints:
```python
ApprovalPresentation(
    type="diff",           # Render as a diff
    content="- old\n+ new",
    language="json",       # Syntax highlight as JSON
    metadata={"path": "config.json"}
)
```

The `approval_callback` can use these hints to render beautifully:
- `type="diff"` → show colored diff
- `type="command"` → show with `$` prefix and bash highlighting
- `type="file_content"` → syntax highlight based on `language`

The package provides the structure; the CLI provides the rendering.

### 6. Why `ApprovalController` with modes?

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

### 7. Why session caching with `remember="session"`?

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

The cache key is `(tool_name, payload)`, so:
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
| 4. Pre-approve in config | ✅ | `pre_approved` list + `needs_approval()` |
| 5. Approve for session | ✅ | `remember="session"` + `ApprovalMemory` |
| 6. Auto-approve all | ✅ | `ApprovalController(mode="approve_all")` |
| 7. Strict mode | ✅ | `ApprovalController(mode="strict")` |
| 8. Shell command approval | ✅ | Any tool can require approval |
| 9. Pattern-based pre-approval | ✅ | `needs_approval()` with pattern matching |
| 10. Block dangerous commands | ✅ | `needs_approval()` raises `PermissionError` |
| 11-13. Worker/delegation approval | ✅ | Generic — any tool type works |
| 14. See approval history | ✅ | `ApprovalMemory.list_approvals()` |
| 15-18. Rich presentation | ✅ | `ApprovalPresentation` with types |

---

## The Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│  • TTY detection (Story 15)                                 │
│  • Rich rendering of ApprovalPresentation                   │
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
│                    ApprovalToolset                          │
│  • Wraps any AbstractToolset                                │
│  • Checks pre_approved list                                 │
│  • Calls needs_approval() on inner toolset                  │
│  • Builds ApprovalRequest with presentation                 │
│  • Consults cache, calls approval_callback, handles decision│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Inner Toolset                            │
│  • Implements actual tool logic                             │
│  • Optionally implements needs_approval() -> bool | dict    │
│  • Controls approval granularity via payload design         │
└─────────────────────────────────────────────────────────────┘
```

Each layer has a single responsibility:
- **CLI**: User interaction and display
- **Controller**: Mode-based behavior and session memory
- **ApprovalToolset**: Approval flow orchestration
- **Inner Toolset**: Domain logic and approval decisions

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

The architecture is designed to be adoptable incrementally — start with `ApprovalToolset` + simple `approval_callback`, add `ApprovalController` when you need modes, add `needs_approval()` when you need per-call decisions.
