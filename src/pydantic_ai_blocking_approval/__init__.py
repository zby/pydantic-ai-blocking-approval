"""Blocking approval system for PydanticAI agent tools.

This package provides human-in-the-loop approval handling for LLM agent tools.
Supports both synchronous blocking callbacks (for CLI) and asynchronous callbacks
(for web UI, Slack bots, etc.).

Key Components:
    - ApprovalResult: Structured result from approval checking (blocked/pre_approved/needs_approval)
    - ApprovalRequest: Returned by tools when approval is needed
    - ApprovalDecision: User's decision (approved, remember for session)
    - ApprovalMemory: Session cache for "approve for session" functionality
    - ApprovalToolset: Unified wrapper (auto-detects inner toolset capabilities)
    - ApprovalController: Mode-based controller (interactive/approve_all/strict)
    - SupportsNeedsApproval: Protocol for toolsets with custom approval logic
    - SupportsApprovalDescription: Protocol for custom approval descriptions
    - ApprovalCallback: Type alias for sync/async approval callbacks

Example with config (simple inner toolset):
    from pydantic_ai import Agent
    from pydantic_ai_blocking_approval import (
        ApprovalController,
        ApprovalDecision,
        ApprovalRequest,
        ApprovalToolset,
    )

    # Create a callback for interactive approval
    def my_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
        print(f"Approve {request.tool_name}? {request.description}")
        response = input("[y/n/s(ession)]: ")
        if response == "s":
            return ApprovalDecision(approved=True, remember="session")
        return ApprovalDecision(approved=response.lower() == "y")

    # Wrap your toolset with config-based approval
    controller = ApprovalController(mode="interactive", approval_callback=my_approval_callback)
    approved_toolset = ApprovalToolset(
        inner=my_toolset,
        approval_callback=controller.approval_callback,
        memory=controller.memory,
        config={
            "safe_tool": {"pre_approved": True},
            # All other tools require approval (secure by default)
        },
    )

    # Use with PydanticAI agent
    agent = Agent(..., toolsets=[approved_toolset])

Example with smart inner toolset (implements SupportsNeedsApproval):
    from pydantic_ai import RunContext
    from pydantic_ai_blocking_approval import ApprovalResult, ApprovalToolset

    class MyToolset(AbstractToolset):
        def needs_approval(self, name: str, tool_args: dict, ctx: RunContext) -> ApprovalResult:
            if name == "forbidden":
                return ApprovalResult.blocked("Not allowed")
            if name == "safe_tool":
                return ApprovalResult.pre_approved()
            return ApprovalResult.needs_approval()

        def get_approval_description(self, name: str, tool_args: dict, ctx: RunContext) -> str:
            return f"Execute: {name}"

    # ApprovalToolset auto-detects needs_approval and delegates to it
    approved = ApprovalToolset(inner=MyToolset(), approval_callback=my_callback)

For testing, use approve_all or strict modes:
    controller = ApprovalController(mode="approve_all")  # Auto-approve
    controller = ApprovalController(mode="strict")       # Auto-deny
"""

from .controller import ApprovalController
from .memory import ApprovalMemory
from .toolset import ApprovalToolset
from .types import (
    ApprovalCallback,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResult,
    SupportsApprovalDescription,
    SupportsNeedsApproval,
)

__version__ = "0.8.0"

__all__ = [
    "ApprovalCallback",
    "ApprovalController",
    "ApprovalDecision",
    "ApprovalMemory",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalToolset",
    "SupportsApprovalDescription",
    "SupportsNeedsApproval",
]
