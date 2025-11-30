"""Core approval types.

This module defines the fundamental data types for the blocking approval system:
- OperationDescriptor: Describes the operation for approval context
- ApprovalRequest: Returned by tools to request approval
- ApprovalDecision: User's decision about a tool call
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class OperationDescriptor(BaseModel):
    """Describes the operation for approval context.

    Optional - tools can provide this for richer approval display.
    If not provided, the approval prompt renders from tool_name + args.
    The CLI layer uses this to decide how to present the operation.

    Attributes:
        type: The type of operation/content (e.g., diff, command, file_content)
        content: The actual content to display
        language: Optional language hint for syntax highlighting
        metadata: Additional operation metadata
    """

    type: Literal["text", "diff", "file_content", "command", "structured"]
    content: str
    language: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """Request for user approval before executing a tool.

    Created by ApprovalToolset when a tool call needs approval.
    Passed to the prompt_fn callback for user decision.

    Attributes:
        tool_name: Name of the tool requesting approval
        description: Human-readable description of what the tool wants to do
        payload: Data for session matching (determines if cached approval applies)
        operation: Optional descriptor of the operation for richer display
    """

    tool_name: str
    description: str
    payload: dict[str, Any]
    operation: Optional[OperationDescriptor] = None


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
