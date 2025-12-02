# TODO

## 1. Refactor: Split ApprovalToolset into Base + Two Variants

### Overview

Split the current `ApprovalToolset` into a class hierarchy:

1. **`BaseApprovalToolset`** - Abstract base with shared approval machinery
2. **`SimpleApprovalToolset`** - Config-based approval (for simple inner toolsets)
3. **`ApprovalToolset`** - Delegates to `inner.needs_approval()` (for smart inner toolsets)

### Class Hierarchy

```python
from abc import abstractmethod

class BaseApprovalToolset(AbstractToolset):
    """Base class with approval machinery. Subclasses implement needs_approval()."""

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

    @abstractmethod
    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        """Subclasses must implement."""
        ...

    async def call_tool(self, name, tool_args, ctx, tool):
        # Shared logic - check needs_approval, prompt, delegate
        ...

    def _prompt_for_approval(self, ...):
        # Shared logic
        ...


class SimpleApprovalToolset(BaseApprovalToolset):
    """Config-based approval. Inner toolset doesn't need needs_approval()."""

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        if self.config.get(name, {}).get("pre_approved"):
            return False
        return True  # Secure by default


class ApprovalToolset(BaseApprovalToolset):
    """Delegates to inner.needs_approval(). For smart inner toolsets."""

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        return self._inner.needs_approval(name, tool_args)
```

### Usage

**Simple toolset (no needs_approval on inner):**
```python
approved = SimpleApprovalToolset(
    inner=my_toolset,
    approval_callback=cb,
    config={"safe_tool": {"pre_approved": True}},
)
```

**Smart toolset (inner implements needs_approval):**
```python
class ShellToolsetInner(AbstractToolset):
    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        command = tool_args.get("command", "")
        if command.startswith("ls "):
            return False
        return {"description": f"Execute: {command}"}

approved = ApprovalToolset(
    inner=ShellToolsetInner(),
    approval_callback=cb,
)
```

### Migration

- Current `ApprovalToolset` users → use `SimpleApprovalToolset`
- Subclasses that override `needs_approval()` → move logic to inner class, use `ApprovalToolset`

---

## 2. Plugin Architecture: Add `create()` Factory

**Depends on:** Part 1 (class hierarchy refactor)

Add `create()` classmethod to `ApprovalToolset` for llm-do plugin architecture.

### Requirements

1. **`inner_class` attribute**: Subclasses set `inner_class` class attribute
2. **Inner toolset convention**: Inner class must accept `(config, context)` in `__init__`
3. **Factory method `create()`** on `ApprovalToolset`

### Implementation

```python
class ApprovalToolset(BaseApprovalToolset):
    """Delegates to inner.needs_approval(). For smart inner toolsets."""

    inner_class: type[AbstractToolset]  # Subclasses set this

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        return self._inner.needs_approval(name, tool_args)

    @classmethod
    def create(
        cls,
        config: dict,
        context: Any,
        approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
    ) -> "ApprovalToolset":
        """Factory method for plugin architecture."""
        if not hasattr(cls, "inner_class"):
            raise NotImplementedError(f"{cls.__name__} must define inner_class attribute")
        inner = cls.inner_class(config, context)
        return cls(
            inner=inner,
            approval_callback=approval_callback,
            memory=memory,
            config=config,
        )
```

### Usage in llm-do

```python
class ShellToolsetInner(AbstractToolset):
    def __init__(self, config: dict, context: Any):
        self._config = config
        self._context = context

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        command = tool_args.get("command", "")
        if command.startswith("ls "):
            return False
        return {"description": f"Execute: {command}"}


class ShellApprovalToolset(ApprovalToolset):
    inner_class = ShellToolsetInner


# In llm-do plugin system:
toolset = ShellApprovalToolset.create(config, context, approval_callback)
```

### Reference

See `/home/zby/llm/llm-do/docs/notes/toolset_plugin_architecture.md` for plugin architecture proposal.
