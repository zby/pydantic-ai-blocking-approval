"""Core approval types.

This module defines the fundamental data types for the blocking approval system:
- ApprovalRequest: Returned by tools to request approval
- ApprovalDecision: User's decision about a tool call
- SupportsNeedsApproval: Protocol for toolsets with custom approval logic
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class SupportsNeedsApproval(Protocol):
    """Protocol for toolsets that implement custom approval logic.

    Toolsets implementing this protocol can provide fine-grained control
    over which tool calls need approval based on the tool name and arguments.

    Example:
        class MyToolset(AbstractToolset):
            def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
                if name == "safe_tool":
                    return False  # No approval needed
                if name == "dangerous_tool":
                    return {"description": "Run dangerous operation"}
                return True  # Default: needs approval
    """

    def needs_approval(self, name: str, tool_args: dict[str, Any]) -> bool | dict[str, Any]:
        """Determine if a tool call needs approval.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool

        Returns:
            False: No approval needed, proceed directly
            True: Approval needed with default description
            dict: Approval needed with custom description ({"description": "..."})
        """
        ...


class ApprovalRequest(BaseModel):
    """Request for user approval before executing a tool.

    Created by ApprovalToolset when a tool call needs approval.
    Passed to the approval_callback for user decision.

    Attributes:
        tool_name: Name of the tool requesting approval
        tool_args: Arguments passed to the tool (used for display and session cache matching)
        description: Human-readable description of what the tool wants to do
    """

    tool_name: str
    tool_args: dict[str, Any]
    description: str


class ApprovalDecision(BaseModel):
    """User's decision about a tool call.

    Returned after the user (or auto-mode) decides whether to approve
    a tool operation.

    Attributes:
        approved: Whether the operation should proceed
        note: Optional reason for rejection or comment
        remember: Whether to cache this decision for the session
    """

    approved: bool
    note: Optional[str] = None
    remember: Literal["none", "session"] = "none"
