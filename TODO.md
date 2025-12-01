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
   ) -> "ApprovalToolset":
   ```

2. **`inner_class` attribute**: Subclasses set `inner_class` class attribute

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
) -> "ApprovalToolset":
    """Factory method for plugin architecture.

    Args:
        config: Toolset configuration dict
        context: Runtime context with dependencies (passed to inner_class)
        approval_callback: Callback for approval decisions
        memory: Optional approval memory for session caching
    """
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

Subclass example:
```python
class ShellApprovalToolset(ApprovalToolset):
    inner_class = ShellToolsetInner

    def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
        # custom logic...
```

### Reference

See `/home/zby/llm/llm-do/docs/notes/toolset_plugin_architecture.md` for full proposal.
