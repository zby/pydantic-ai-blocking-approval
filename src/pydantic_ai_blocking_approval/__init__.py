"""Synchronous, blocking approval system for PydanticAI agent tools.

This package provides human-in-the-loop approval handling for LLM agent tools.
Unlike deferred/async approval patterns, this system blocks execution until
the user decides, making it ideal for CLI and interactive use cases where
the user is present at the terminal.

Key Components:
    - ApprovalRequest: Returned by tools when approval is needed
    - ApprovalDecision: User's decision (approved, remember for session)
    - ApprovalMemory: Session cache for "approve for session" functionality
    - ApprovalToolset: Wrapper that intercepts tool calls for approval
    - ApprovalController: Mode-based controller (interactive/approve_all/strict)

Example:
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

    # Wrap your toolset with approval using per-tool config
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

For testing, use approve_all or strict modes:
    controller = ApprovalController(mode="approve_all")  # Auto-approve
    controller = ApprovalController(mode="strict")       # Auto-deny

For custom approval logic, subclass ApprovalToolset and override needs_approval():
    class MyApprovalToolset(ApprovalToolset):
        def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
            # Custom logic here
            ...
"""

from .controller import ApprovalController
from .memory import ApprovalMemory
from .toolset import ApprovalToolset
from .types import ApprovalDecision, ApprovalRequest

__version__ = "0.4.0"

__all__ = [
    "ApprovalController",
    "ApprovalDecision",
    "ApprovalMemory",
    "ApprovalRequest",
    "ApprovalToolset",
]
