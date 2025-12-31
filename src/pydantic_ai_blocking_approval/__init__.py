"""Blocking approval system for PydanticAI agent tools.

This package provides human-in-the-loop approval handling for LLM agent tools.
Supports both synchronous blocking callbacks (for CLI) and asynchronous callbacks
(for web UI, Slack bots, etc.).

Key Components:
    - ApprovalResult: Structured result from approval checking (blocked/pre_approved/needs_approval)
    - ApprovalRequest: Returned by tools when approval is needed
    - ApprovalDecision: User's decision (approved, note, remember hint)
    - ApprovalError: Base exception for approval failures
    - ApprovalDenied: Exception raised when a tool call is denied
    - ApprovalBlocked: Exception raised when a tool call is blocked by policy
    - ApprovalToolset: Unified wrapper (auto-detects inner toolset capabilities)
    - SupportsNeedsApproval: Protocol for toolsets with custom approval logic
    - SupportsApprovalDescription: Protocol for custom approval descriptions
    - ApprovalCallback: Type alias for sync/async approval callbacks

Example with config (simple inner toolset):
    from pydantic_ai import Agent
    from pydantic_ai_blocking_approval import (
        ApprovalDecision,
        ApprovalRequest,
        ApprovalToolset,
    )

    # Create a callback for interactive approval
    def my_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
        print(f"Approve {request.tool_name}? {request.description}")
        response = input("[y/n]: ")
        return ApprovalDecision(approved=response.lower() == "y")

    # Wrap your toolset with config-based approval
    approved_toolset = ApprovalToolset(
        inner=my_toolset,
        approval_callback=my_approval_callback,
        config={
            "safe_tool": {"pre_approved": True},
            # All other tools require approval (secure by default)
        },
    )

    # Use with PydanticAI agent
    agent = Agent(..., toolsets=[approved_toolset])

Example with smart inner toolset (implements SupportsNeedsApproval):
    from typing import Any

    from pydantic_ai import RunContext
    from pydantic_ai_blocking_approval import (
        ApprovalResult,
        ApprovalToolset,
        needs_approval_from_config,
    )

    class MyToolset(AbstractToolset):
        def needs_approval(
            self,
            name: str,
            tool_args: dict,
            ctx: RunContext,
            config: dict[str, dict[str, Any]],
        ) -> ApprovalResult:
            base = needs_approval_from_config(name, config)
            if base.is_pre_approved:
                return base
            if name == "forbidden":
                return ApprovalResult.blocked("Not allowed")
            if name == "safe_tool":
                return ApprovalResult.pre_approved()
            return ApprovalResult.needs_approval()

        def get_approval_description(self, name: str, tool_args: dict, ctx: RunContext) -> str:
            return f"Execute: {name}"

    # ApprovalToolset auto-detects needs_approval and delegates to it
    approved = ApprovalToolset(inner=MyToolset(), approval_callback=my_callback)

For testing, use approve-all or strict callbacks:
    def approve_all(_: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=True)

    def deny_all(_: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, note="Strict mode")
"""

from .toolset import ApprovalToolset
from .types import (
    ApprovalConfig,
    ApprovalCallback,
    ApprovalBlocked,
    ApprovalDecision,
    ApprovalDenied,
    ApprovalError,
    ApprovalRequest,
    ApprovalResult,
    SupportsApprovalDescription,
    SupportsNeedsApproval,
    needs_approval_from_config,
)

__version__ = "0.9.0"

__all__ = [
    "ApprovalConfig",
    "ApprovalCallback",
    "ApprovalBlocked",
    "ApprovalDecision",
    "ApprovalDenied",
    "ApprovalError",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalToolset",
    "SupportsApprovalDescription",
    "SupportsNeedsApproval",
    "needs_approval_from_config",
]
