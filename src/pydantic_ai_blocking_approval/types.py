"""Core approval types.

This module defines the fundamental data types for the blocking approval system:
- ApprovalRequest: Returned by tools to request approval
- ApprovalDecision: User's decision about a tool call
"""
from __future__ import annotations

from typing import Any, Literal, Optional  # noqa: F401 - Literal used in ApprovalDecision

from pydantic import BaseModel


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
