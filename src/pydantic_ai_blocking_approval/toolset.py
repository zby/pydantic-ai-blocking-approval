"""Approval toolset wrapper for PydanticAI toolsets.

This module provides the ApprovalToolset wrapper that intercepts tool calls
for approval checking. It automatically detects whether the inner toolset
implements SupportsNeedsApproval protocol and delegates accordingly.
"""
from __future__ import annotations

import inspect
from typing import Any, Optional

from pydantic_ai import RunContext
from pydantic_ai.toolsets import AbstractToolset

from .memory import ApprovalMemory
from .types import (
    ApprovalCallback,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResult,
    SupportsApprovalDescription,
    SupportsNeedsApproval,
)


class ApprovalToolset(AbstractToolset):
    """Approval wrapper for PydanticAI toolsets.

    Intercepts tool calls and prompts for user approval before execution.
    Automatically detects if the inner toolset implements `SupportsNeedsApproval`:

    - If inner implements SupportsNeedsApproval: delegates approval decision to it
    - Otherwise: uses config dict to determine pre-approved tools (secure by default)

    Example with config (simple inner toolset):
        approved = ApprovalToolset(
            inner=my_toolset,
            approval_callback=my_callback,
            config={
                "get_time": {"pre_approved": True},
                "list_files": {"pre_approved": True},
                # All other tools require approval
            },
        )

    Example with smart inner toolset:
        class MyToolset(AbstractToolset):
            def needs_approval(self, name: str, tool_args: dict, ctx: RunContext) -> ApprovalResult:
                if name == "forbidden":
                    return ApprovalResult.blocked("Not allowed")
                if name == "safe_tool":
                    return ApprovalResult.pre_approved()
                return ApprovalResult.needs_approval()

            def get_approval_description(self, name: str, tool_args: dict, ctx: RunContext) -> str:
                return f"Execute: {name}"

        approved = ApprovalToolset(
            inner=MyToolset(),
            approval_callback=my_callback,
        )
    """

    def __init__(
        self,
        inner: AbstractToolset,
        approval_callback: ApprovalCallback,
        memory: Optional[ApprovalMemory] = None,
        config: Optional[dict[str, dict[str, Any]]] = None,
    ):
        """Initialize the approval wrapper.

        Args:
            inner: The toolset to wrap (must implement AbstractToolset)
            approval_callback: Callback to request user approval. Can be sync or async.
                Sync callbacks block until decision is made.
                Async callbacks can await external approval (e.g., from web UI).
            memory: Session cache for "approve for session" (created if None)
            config: Per-tool configuration dict. Each key is a tool name, value is
                a dict with optional "pre_approved": True to skip approval.
                Only used when inner doesn't implement SupportsNeedsApproval.
        """
        self._inner = inner
        self._approval_callback = approval_callback
        self._memory = memory or ApprovalMemory()
        self.config = config or {}

    @property
    def id(self) -> Optional[str]:
        """Delegate to inner toolset's id."""
        return getattr(self._inner, "id", None)

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to inner toolset."""
        return getattr(self._inner, name)

    async def get_tools(self, ctx: Any) -> dict:
        """Delegate to inner toolset's get_tools."""
        return await self._inner.get_tools(ctx)

    def _get_approval_result(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any]
    ) -> ApprovalResult:
        """Get approval result from inner toolset or config."""
        if isinstance(self._inner, SupportsNeedsApproval):
            return self._inner.needs_approval(name, tool_args, ctx)

        # Config-based fallback (secure by default)
        tool_config = self.config.get(name, {})
        if tool_config.get("pre_approved"):
            return ApprovalResult.pre_approved()
        return ApprovalResult.needs_approval()

    def _get_description(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any]
    ) -> str:
        """Get description from inner toolset or generate default."""
        if isinstance(self._inner, SupportsApprovalDescription):
            return self._inner.get_approval_description(name, tool_args, ctx)

        # Default: "tool_name(arg1=val1, arg2=val2)"
        args_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items())
        return f"{name}({args_str})"

    async def _prompt_for_approval(
        self, name: str, tool_args: dict[str, Any], description: str
    ) -> None:
        """Prompt user for approval. Raises PermissionError if denied.

        Supports both sync and async approval callbacks. Sync callbacks are
        called directly; async callbacks are awaited.
        """
        # Check session cache first
        cached = self._memory.lookup(name, tool_args)
        if cached is not None and cached.approved:
            return

        request = ApprovalRequest(
            tool_name=name,
            tool_args=tool_args,
            description=description,
        )

        # Handle both sync and async callbacks
        result = self._approval_callback(request)
        if inspect.isawaitable(result):
            decision = await result
        else:
            decision = result

        self._memory.store(name, tool_args, decision)

        if not decision.approved:
            raise PermissionError(
                f"User denied {name}: {decision.note or 'no reason given'}"
            )

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: Any,
    ) -> Any:
        """Intercept tool calls for approval checking."""
        result = self._get_approval_result(name, tool_args, ctx)

        if result.is_blocked:
            raise PermissionError(result.block_reason)

        if result.is_needs_approval:
            description = self._get_description(name, tool_args, ctx)
            await self._prompt_for_approval(name, tool_args, description)

        return await self._inner.call_tool(name, tool_args, ctx, tool)
