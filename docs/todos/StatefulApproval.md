# Future Consideration: Method-Based Approval

> **Status**: Design discussion. No changes planned yet.

This document captures a discussion about potentially converting `approval_callback` from a constructor parameter to an overridable method.

---

## Current Design (Callback-Based)

```python
toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=my_callback,
)
```

**Characteristics:**
- Functional composition — pass a callable
- Concise for testing (`approval_callback=lambda req: ApprovalDecision(approved=True)`)
- Easy integration with `ApprovalController`
- Callback receives only the `ApprovalRequest`, no access to toolset state

---

## Alternative Design (Method-Based)

```python
class MyApprovalToolset(ApprovalToolset):
    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        # Has access to self — can use instance state
        print(f"Approve {request.tool_name}?")
        return ApprovalDecision(approved=input("[y/n]: ") == "y")

toolset = MyApprovalToolset(inner=my_toolset)
```

**Characteristics:**
- Classic OOP pattern — subclass and override
- Method has access to `self` — can use instance state
- Clear contract — method signature explicit in class
- Requires subclassing for every customization

---

## Key Question: Does Approval Logic Need Instance State?

### Current Instance State in ApprovalToolset

```python
self._inner          # The wrapped toolset
self._approval_callback
self._memory         # ApprovalMemory for session caching
self._pre_approved   # Set of pre-approved tool names
```

### Scenarios Where Instance Access Could Be Useful

**1. Approval metrics/logging**
```python
def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
    self._approval_count += 1
    self._last_approval_time = datetime.now()
    # ... actual approval logic
```
*Assessment*: Useful, but achievable externally by wrapping the callback.

**2. Dynamic behavior based on approval history**
```python
def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
    # Auto-approve if user approved 5+ similar requests this session
    similar_approvals = self._memory.count_approvals_for(request.tool_name)
    if similar_approvals >= 5:
        return ApprovalDecision(approved=True, note="Auto-approved (pattern)")
    # ... prompt user
```
*Assessment*: Compelling. Direct access to `self._memory` enables smarter UX without duplicating cache logic.

**3. Access to inner toolset for context**
```python
def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
    if hasattr(self._inner, 'get_risk_level'):
        risk = self._inner.get_risk_level(request.tool_name)
        if risk == "low":
            return ApprovalDecision(approved=True)
    # ... prompt user
```
*Assessment*: Interesting, but arguably belongs in `needs_approval()` on the inner toolset.

**4. Conditional pre-approval modification**
```python
def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
    # After 3 approvals of same tool, offer to add to pre_approved
    if self._should_suggest_preapproval(request.tool_name):
        if self._prompt_add_to_preapproved(request.tool_name):
            self._pre_approved.add(request.tool_name)
            return ApprovalDecision(approved=True)
    # ... prompt user
```
*Assessment*: Powerful UX feature that requires instance access.

---

## Analysis Summary

The current callback design handles **stateless** approval decisions well. The most common stateful concern (session caching) is already handled by `ApprovalMemory`, which is consulted *before* the callback is invoked.

However, **advanced UX patterns** would benefit from instance access:
- "You've approved this 5 times, want to approve for session?"
- "You always approve `list_files`, add to pre-approved?"
- Approval latency tracking, rejection rate analytics

---

## Possible Hybrid Approach

Support both patterns — callbacks for simple cases, subclassing for complex ones:

```python
class ApprovalToolset(AbstractToolset):
    def __init__(
        self,
        inner: AbstractToolset,
        approval_callback: Optional[Callable[...]] = None,  # Now optional
        ...
    ):
        self._approval_callback = approval_callback

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Override this method OR pass approval_callback to __init__."""
        if self._approval_callback:
            return self._approval_callback(request)
        raise NotImplementedError(
            "Either pass approval_callback or subclass and override request_approval()"
        )
```

**Trade-offs:**
- More flexible API
- Two ways to do the same thing (potential confusion)
- Migration path: start with callbacks, graduate to subclassing when needed

---

## Conclusion

No immediate changes needed. The current callback design serves the core use case well. If future requirements demand stateful approval logic (metrics, adaptive behavior, dynamic pre-approval), the hybrid approach provides a migration path without breaking existing code.

**Decision criteria for revisiting:**
- Building a production CLI that needs approval analytics
- Users requesting "suggest pre-approval after N approvals" feature
- Need to access inner toolset state during approval decisions
