# TODO

## 1. Plugin Architecture: Add `create()` Factory

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
