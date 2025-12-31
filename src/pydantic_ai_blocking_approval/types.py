"""Core approval types.

This module defines the fundamental data types for the blocking approval system:
- ApprovalResult: Structured result from approval checking
- ApprovalRequest: Returned by tools to request approval
- ApprovalDecision: User's decision about a tool call
- SupportsNeedsApproval: Protocol for toolsets with custom approval logic
- SupportsApprovalDescription: Protocol for custom approval descriptions
- ApprovalCallback: Type alias for sync/async approval callbacks
- ApprovalConfig: Mapping type for per-tool config
- needs_approval_from_config: Helper for default config-based decisions
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Mapping, Optional, Protocol, Union, runtime_checkable

from pydantic import BaseModel
from pydantic_ai import RunContext


@dataclass(frozen=True)
class ApprovalResult:
    """Result of checking if a tool call needs approval.

    Use factory methods to create instances:
    - ApprovalResult.blocked(reason) - Operation forbidden by policy
    - ApprovalResult.pre_approved() - No user prompt needed
    - ApprovalResult.needs_approval() - Requires user approval
    """

    status: Literal["blocked", "pre_approved", "needs_approval"]
    block_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status == "blocked" and self.block_reason is None:
            raise ValueError("blocked ApprovalResult requires block_reason")
        if self.status != "blocked" and self.block_reason is not None:
            raise ValueError("block_reason is only valid for blocked status")

    @classmethod
    def blocked(cls, reason: str) -> "ApprovalResult":
        """Operation is forbidden by policy."""
        return cls(status="blocked", block_reason=reason)

    @classmethod
    def pre_approved(cls) -> "ApprovalResult":
        """Operation is pre-approved, no user prompt needed."""
        return cls(status="pre_approved")

    @classmethod
    def needs_approval(cls) -> "ApprovalResult":
        """Operation requires user approval."""
        return cls(status="needs_approval")

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def is_pre_approved(self) -> bool:
        return self.status == "pre_approved"

    @property
    def is_needs_approval(self) -> bool:
        return self.status == "needs_approval"


ApprovalConfig = Mapping[str, Mapping[str, Any]]


@runtime_checkable
class SupportsNeedsApproval(Protocol):
    """Protocol for toolsets with custom approval logic.

    Toolsets implementing this protocol provide fine-grained control
    over which tool calls are blocked, pre-approved, or need user approval.

    Example:
        class MyToolset(AbstractToolset):
            def needs_approval(
                self,
                name: str,
                tool_args: dict,
                ctx: RunContext,
                config: ApprovalConfig,
            ) -> ApprovalResult:
                base = needs_approval_from_config(name, config)
                if base.is_pre_approved:
                    return base
                if name == "forbidden_tool":
                    return ApprovalResult.blocked("Tool is disabled")
                if name == "safe_tool":
                    return ApprovalResult.pre_approved()
                return ApprovalResult.needs_approval()
    """

    def needs_approval(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        config: ApprovalConfig,
    ) -> ApprovalResult | Awaitable[ApprovalResult]:
        """Determine approval status for a tool call.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool
            ctx: PydanticAI run context
            config: ApprovalToolset config passed through from the wrapper

        Returns:
            ApprovalResult with status: blocked, pre_approved, or needs_approval
        """
        ...


@runtime_checkable
class SupportsApprovalDescription(Protocol):
    """Protocol for toolsets that provide custom approval descriptions.

    Optional protocol. If not implemented, ApprovalToolset generates
    a default description from tool name and arguments.
    """

    def get_approval_description(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any]
    ) -> str:
        """Return human-readable description for approval prompt.

        Only called when needs_approval() returns needs_approval status.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool
            ctx: PydanticAI run context

        Returns:
            Description string to show user (e.g., "Execute: git status")
        """
        ...


class ApprovalRequest(BaseModel):
    """Request for user approval before executing a tool.

    Created by ApprovalToolset when a tool call needs approval.
    Passed to the approval_callback for user decision.

    Attributes:
        tool_name: Name of the tool requesting approval
        tool_args: Arguments passed to the tool (used for display and caller-side caching)
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
        remember: Optional hint for caller-managed session caching
    """

    approved: bool
    note: Optional[str] = None
    remember: Literal["none", "session"] = "none"


class ApprovalError(PermissionError):
    """Base exception for approval-related failures."""

    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name


class ApprovalDenied(ApprovalError):
    """Exception raised when a user denies a tool call."""

    def __init__(self, tool_name: str, decision: "ApprovalDecision") -> None:
        note = decision.note or "no reason given"
        super().__init__(tool_name, f"Approval denied for {tool_name}: {note}")
        self.decision = decision


class ApprovalBlocked(ApprovalError):
    """Exception raised when a tool call is blocked by policy."""

    def __init__(self, tool_name: str, reason: Optional[str]) -> None:
        message = reason or "blocked by policy"
        super().__init__(tool_name, f"Blocked {tool_name}: {message}")
        self.reason = reason


def ensure_decision(result: Any) -> "ApprovalDecision":
    """Ensure callback results are ApprovalDecision."""
    if isinstance(result, ApprovalDecision):
        return result
    raise TypeError("approval_callback must return ApprovalDecision")


def needs_approval_from_config(
    name: str, config: ApprovalConfig | None
) -> ApprovalResult:
    """Default approval decision from config (secure by default)."""
    tool_config = (config or {}).get(name, {})
    if tool_config.get("pre_approved"):
        return ApprovalResult.pre_approved()
    return ApprovalResult.needs_approval()


# Type alias for approval callbacks - supports both sync/async decisions
ApprovalCallback = Callable[
    ["ApprovalRequest"],
    Union["ApprovalDecision", Awaitable["ApprovalDecision"]]
]
