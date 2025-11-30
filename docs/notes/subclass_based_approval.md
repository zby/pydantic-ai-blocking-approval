# Subclass-Based Approval Design

**Status:** Proposed
**Date:** 2025-11-30

## Summary

Replace the current approval mechanism (inner toolset's `needs_approval()` + `pre_approved` list) with a simpler subclass-based approach where `ApprovalToolset.needs_approval()` is a public method that subclasses override.

## Current Design

```
ApprovalToolset
    ├── pre_approved: list[str]           # Tools that skip approval
    ├── checks @requires_approval decorator
    ├── calls inner.needs_approval()      # If inner toolset implements it
    └── complex precedence rules
```

**Problems:**
1. Multiple mechanisms (list, decorator, inner method) with unclear precedence
2. Inner toolset must know about approval (leaky abstraction)
3. `ApprovalConfigurable` protocol adds complexity
4. Hard to customize without understanding all the layers

## Proposed Design

```
ApprovalToolset
    ├── config: dict[str, dict]           # Per-tool configuration
    └── needs_approval(name, args)        # Override in subclass
```

**Key changes:**
1. `needs_approval()` is a public method on `ApprovalToolset` itself
2. Subclasses override it for custom logic
3. Per-tool config dict replaces `pre_approved` list
4. Inner toolset has no approval awareness

### Base Implementation

```python
class ApprovalToolset(AbstractToolset):
    def __init__(
        self,
        inner: AbstractToolset,
        approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
        config: Optional[dict[str, dict[str, Any]]] = None,
    ):
        self._inner = inner
        self._approval_callback = approval_callback
        self._memory = memory or ApprovalMemory()
        self.config = config or {}

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        """Determine if this tool call needs approval.

        Override in subclass for custom logic.

        Args:
            name: Tool name
            tool_args: Arguments passed to the tool

        Returns:
            False: no approval needed
            True: approval needed with default description
            dict: approval needed with custom description ({"description": "..."})
        """
        tool_config = self.config.get(name, {})
        if tool_config.get("pre_approved"):
            return False
        return True  # Secure by default

    async def call_tool(self, name, tool_args, ctx, tool):
        result = self.needs_approval(name, tool_args)
        if result is not False:
            custom = result if isinstance(result, dict) else None
            self._prompt_for_approval(name, tool_args, custom)
        return await self._inner.call_tool(name, tool_args, ctx, tool)
```

### Usage: Simple Case

```python
# Pre-approve specific tools via config
toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=callback,
    config={
        "get_time": {"pre_approved": True},
        "list_files": {"pre_approved": True},
        # All other tools require approval (secure by default)
    },
)
```

### Usage: Custom Logic via Subclass

```python
class ShellApprovalToolset(ApprovalToolset):
    """Shell command approval with pattern matching.

    Config per tool:
        pre_approved: bool - skip approval entirely
        safe_commands: list[str] - command prefixes that skip approval
        dangerous_patterns: list[str] - regex patterns that require approval
    """

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        tool_config = self.config.get(name, {})

        # Check pre_approved first
        if tool_config.get("pre_approved"):
            return False

        # For shell_exec, do pattern matching
        if name == "shell_exec":
            command = tool_args.get("command", "")
            base = command.split()[0] if command else ""

            # Safe commands
            safe = tool_config.get("safe_commands", [])
            if base in safe:
                return False

            # Dangerous patterns
            for pattern in tool_config.get("dangerous_patterns", []):
                if re.search(pattern, command):
                    return {"description": f"Dangerous command: {command}"}

            return {"description": f"Execute: {command}"}

        # Default for other tools
        return True


# Usage
toolset = ShellApprovalToolset(
    inner=shell_toolset,
    approval_callback=callback,
    config={
        "shell_exec": {
            "safe_commands": ["ls", "pwd", "echo", "date"],
            "dangerous_patterns": [r"\brm\b", r"\bsudo\b", r"\|", r">"],
        },
    },
)
```

### Usage: File Sandbox Approval

```python
class SandboxApprovalToolset(ApprovalToolset):
    """File sandbox approval based on paths.

    Config per tool:
        pre_approved: bool - skip approval entirely
        safe_paths: list[str] - path prefixes that skip approval
    """

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        tool_config = self.config.get(name, {})

        if tool_config.get("pre_approved"):
            return False

        # For file operations, check path
        if name in ("write_file", "delete_file", "patch_file"):
            path = tool_args.get("path", "")
            safe_paths = tool_config.get("safe_paths", [])

            if any(path.startswith(safe) for safe in safe_paths):
                return False

            return {"description": f"{name}: {path}"}

        if name == "read_file":
            # Reads might be pre-approved differently
            return tool_config.get("require_read_approval", False)

        return True


# Usage
toolset = SandboxApprovalToolset(
    inner=file_sandbox,
    approval_callback=callback,
    config={
        "write_file": {
            "safe_paths": ["./cache/", "./tmp/"],
        },
        "read_file": {
            "pre_approved": True,  # All reads OK
        },
        "delete_file": {},  # Always requires approval
    },
)
```

## What This Removes

1. **`pre_approved` parameter** - replaced by `config[tool_name]["pre_approved"]`
2. **Inner toolset's `needs_approval()`** - approval logic lives in wrapper only
3. **`ApprovalConfigurable` protocol** - no longer needed
4. **`@requires_approval` decorator** - redundant when config is the source of truth
5. **Complex precedence rules** - single method, clear logic

## What This Adds

1. **`config` parameter** - per-tool configuration dict
2. **Public `needs_approval()` method** - override point for subclasses

## Benefits

1. **Standard OO** - subclass and override, no new concepts
2. **Single source of truth** - `needs_approval()` is the only decision point
3. **Flexible config** - each subclass defines its own config schema
4. **Clear ownership** - `ApprovalToolset` owns approval, inner toolset is unaware
5. **Testable** - easy to test `needs_approval()` in isolation

## Migration

### From `pre_approved` list

```python
# Old
ApprovalToolset(
    inner=toolset,
    pre_approved=["tool_a", "tool_b"],
)

# New
ApprovalToolset(
    inner=toolset,
    config={
        "tool_a": {"pre_approved": True},
        "tool_b": {"pre_approved": True},
    },
)
```

### From inner `needs_approval()`

```python
# Old: inner toolset implements needs_approval()
class MyToolset(AbstractToolset):
    def needs_approval(self, name, args):
        # custom logic
        ...

ApprovalToolset(inner=MyToolset(), ...)

# New: subclass ApprovalToolset instead
class MyApprovalToolset(ApprovalToolset):
    def needs_approval(self, name, args):
        # custom logic (same as before)
        ...

MyApprovalToolset(inner=BasicToolset(), ...)
```

## Design Decisions

### No `@requires_approval` decorator

The decorator is removed entirely. With config as the single source of truth:
- Default behavior is "require approval" (secure by default)
- To skip approval, explicitly set `{"pre_approved": True}`
- No need for a decorator that just says "require approval" - that's already the default

This eliminates a mechanism that would otherwise need precedence rules with config.

### Secure by default for unknown tools

Tools not in config require approval. This is the safe default:
- Forgetting to configure a tool = extra prompts (annoying but safe)
- Forgetting to configure a dangerous tool ≠ security hole

### Config validation

Config validation is **the subclass's responsibility**. Options:

**1. No validation (simple)**
```python
class MyApprovalToolset(ApprovalToolset):
    def needs_approval(self, name, tool_args):
        tool_config = self.config.get(name, {})
        # Just use .get() with defaults, ignore unknown keys
        if tool_config.get("pre_approved"):
            return False
        return True
```

**2. Validate in `__init__` (defensive)**
```python
class ShellApprovalToolset(ApprovalToolset):
    VALID_KEYS = {"pre_approved", "safe_commands", "dangerous_patterns"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for tool_name, tool_config in self.config.items():
            unknown = set(tool_config.keys()) - self.VALID_KEYS
            if unknown:
                raise ValueError(f"Unknown config keys for {tool_name}: {unknown}")
```

**3. Pydantic models (type-safe)**
```python
from pydantic import BaseModel

class ShellToolConfig(BaseModel):
    pre_approved: bool = False
    safe_commands: list[str] = []
    dangerous_patterns: list[str] = []

class ShellApprovalToolset(ApprovalToolset):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Validate and parse config
        self._parsed_config = {
            name: ShellToolConfig(**cfg)
            for name, cfg in self.config.items()
        }

    def needs_approval(self, name, tool_args):
        cfg = self._parsed_config.get(name, ShellToolConfig())
        if cfg.pre_approved:
            return False
        # ... use cfg.safe_commands, cfg.dangerous_patterns
```

**Recommendation:** Start with option 1 (no validation) for the base class. Subclasses can add validation as needed. Pydantic models are overkill for simple cases but useful for complex configs with many options.

## Conclusion

This design simplifies the approval system by:
- Moving from "multiple mechanisms with precedence" to "one overridable method"
- Using standard OO patterns (subclass and override)
- Config as single source of truth (no decorator)
- Secure by default for unknown tools

The tradeoff is that complex approval logic requires a subclass rather than just implementing a protocol on the inner toolset. This is acceptable because:
- Approval is a cross-cutting concern that belongs in the wrapper
- Subclassing is explicit and easy to understand
- Most users will use the base class with simple config
