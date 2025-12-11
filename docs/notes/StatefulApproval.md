# Design Note: Callback vs Method-Based Approval

## Background

`ApprovalToolset` needs a way to prompt users for approval. Two patterns exist:

1. **Callback**: pass a function to the constructor
2. **Method**: subclass and override a method

Both can achieve the same result. This note compares them.

## Current Design: Callbacks

```python
def my_prompt(request: ApprovalRequest) -> ApprovalDecision:
    response = input(f"Approve {request.tool_name}? [y/n/s]: ")
    if response == "s":
        return ApprovalDecision(approved=True, remember="session")
    return ApprovalDecision(approved=response == "y")

toolset = ApprovalToolset(
    inner=my_toolset,
    approval_callback=my_prompt,
)
```

The framework handles everything except the prompt itself:
- Checking `needs_approval()`
- Looking up session cache
- Storing decisions when `remember="session"`

The callback only implements the user interaction.

## Alternative: Method-Based

```python
class MyApprovalToolset(MethodApprovalToolset):
    async def prompt_for_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        response = input(f"Approve {request.tool_name}? [y/n/s]: ")
        if response == "s":
            return ApprovalDecision(approved=True, remember="session")
        return ApprovalDecision(approved=response == "y")

toolset = MyApprovalToolset(inner=my_toolset)
```

Same separation of concerns - subclass only implements the prompt, parent handles the rest.

## Comparison

| Aspect | Callback | Method |
|--------|----------|--------|
| Define behavior | Pass function | Subclass |
| Access to `self` | Via closure | Direct |
| Testing | Lambda/mock function | Mock class |
| Style | Functional | OOP |

## Recommendation

Use callbacks (current design). They're simpler for most cases. A method-based class could be added for users who prefer OOP, but it would be functionally equivalent.
