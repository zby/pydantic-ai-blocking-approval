# TODO

## Plugin Architecture Support

Add `create()` classmethod to `ApprovalToolset` for llm-do plugin architecture.

### Requirements

1. **Factory method `create()`** on `ApprovalToolset`:
   ```python
   @classmethod
   def create(
       cls,
       config: dict,
       context: Any,
       approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
       memory: Optional[ApprovalMemory] = None,
       inner_class: Optional[type[AbstractToolset]] = None,
   ) -> "ApprovalToolset":
   ```

2. **`default_inner_class` pattern**: Subclasses set `default_inner_class` attribute; `create()` uses it when `inner_class` param is None

3. **Inner toolset convention**: Inner class must accept `(config, context)` in `__init__`

### Implementation

```python
@classmethod
def create(
    cls,
    config: dict,
    context: Any,
    approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
    memory: Optional[ApprovalMemory] = None,
    inner_class: Optional[type[AbstractToolset]] = None,
) -> "ApprovalToolset":
    """Factory method for plugin architecture.

    Args:
        config: Toolset configuration dict
        context: Runtime context with dependencies (passed to inner_class)
        approval_callback: Callback for approval decisions
        memory: Optional approval memory for session caching
        inner_class: The inner toolset class to instantiate. If None, uses
            cls.default_inner_class (subclasses should set this).
    """
    actual_inner_class = inner_class or getattr(cls, "default_inner_class", None)
    if actual_inner_class is None:
        raise NotImplementedError(
            f"{cls.__name__} must set default_inner_class or pass inner_class"
        )
    inner = actual_inner_class(config, context)
    return cls(
        inner=inner,
        approval_callback=approval_callback,
        memory=memory,
        config=config,
    )
```

### Usage in llm-do

Subclass example:
```python
class ShellApprovalToolset(ApprovalToolset):
    default_inner_class = ShellToolsetInner

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        # custom logic...
```

Config can override inner class:
```yaml
toolsets:
  llm_do.shell_toolset.ShellApprovalToolset:
    inner_class: custom.MyShellInner  # optional override
    rules: [...]
```

### Reference

See `/home/zby/llm/llm-do/docs/notes/toolset_plugin_architecture.md` for full proposal.
