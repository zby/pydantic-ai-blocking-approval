"""ApprovalToolset wrapper for PydanticAI toolsets.

This module provides ApprovalToolset, which wraps any PydanticAI toolset
and intercepts tool calls for approval checking.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic_ai.toolsets import AbstractToolset

from .memory import ApprovalMemory
from .types import ApprovalDecision, ApprovalRequest


class ApprovalToolset(AbstractToolset):
    """Wraps a toolset with synchronous approval checking.

    This wrapper intercepts all tool calls and checks if approval is needed
    before delegating to the inner toolset.

    Approval is determined by the `needs_approval()` method, which can be
    overridden in subclasses for custom logic. The default implementation
    uses per-tool config to decide.

    **Secure by default**: Tools not configured as pre_approved require approval.

    Example:
        from pydantic_ai import Agent
        from pydantic_ai_blocking_approval import ApprovalToolset

        def my_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
            print(f"Approve {request.tool_name}? {request.description}")
            return ApprovalDecision(approved=input("[y/n]: ").lower() == "y")

        # Simple case: pre-approve safe tools via config
        approved_toolset = ApprovalToolset(
            inner=my_toolset,
            approval_callback=my_approval_callback,
            config={
                "get_time": {"pre_approved": True},
                "list_files": {"pre_approved": True},
                # All other tools require approval (secure by default)
            },
        )

    For custom approval logic, subclass and override `needs_approval()`:

        class ShellApprovalToolset(ApprovalToolset):
            def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
                tool_config = self.config.get(name, {})
                if tool_config.get("pre_approved"):
                    return False

                command = tool_args.get("command", "")
                if command.startswith("ls "):
                    return False  # Safe
                return {"description": f"Execute: {command}"}
    """

    def __init__(
        self,
        inner: AbstractToolset,
        approval_callback: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
        config: Optional[dict[str, dict[str, Any]]] = None,
    ):
        """Initialize the approval wrapper.

        Args:
            inner: The toolset to wrap (must implement AbstractToolset)
            approval_callback: Callback to request user approval (blocks until decision)
            memory: Session cache for "approve for session" (created if None)
            config: Per-tool configuration dict. Each key is a tool name, value is
                a dict of settings. The base class recognizes {"pre_approved": True}
                to skip approval. Subclasses can define additional config keys.
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

    def needs_approval(self, name: str, tool_args: dict[str, Any]) -> bool | dict:
        """Determine if this tool call needs approval.

        Override in subclass for custom approval logic.

        The default implementation checks config[tool_name]["pre_approved"].
        Tools not in config or without pre_approved=True require approval
        (secure by default).

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool

        Returns:
            False: no approval needed
            True: approval needed with default description
            dict: approval needed with custom description ({"description": "..."})
        """
        tool_config = self.config.get(name, {})
        if tool_config.get("pre_approved"):
            return False
        return True  # Secure by default

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: Any,
        tool: Any,
    ) -> Any:
        """Intercept tool calls for approval.

        Calls needs_approval() to determine if approval is needed, then
        prompts user if necessary before delegating to inner toolset.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool
            ctx: PydanticAI run context
            tool: The tool object/function

        Returns:
            Result from the inner toolset's call_tool

        Raises:
            PermissionError: If user denies approval
        """
        result = self.needs_approval(name, tool_args)

        if result is not False:
            custom = result if isinstance(result, dict) else None
            self._prompt_for_approval(name, tool_args, custom)

        return await self._inner.call_tool(name, tool_args, ctx, tool)

    def _prompt_for_approval(
        self,
        name: str,
        tool_args: dict[str, Any],
        custom: Optional[dict[str, Any]] = None,
    ) -> None:
        """Prompt user for approval, raising PermissionError if denied.

        Args:
            name: Tool name
            tool_args: Tool arguments
            custom: Optional dict with custom 'description' key
        """
        if custom is None:
            custom = {}

        description = custom.get(
            "description",
            f"{name}({', '.join(f'{k}={v!r}' for k, v in tool_args.items())})",
        )

        # Check session cache first (keyed by tool_name + tool_args)
        cached = self._memory.lookup(name, tool_args)
        if cached is not None and cached.approved:
            return  # Already approved in session

        # Build request and prompt user
        request = ApprovalRequest(
            tool_name=name,
            tool_args=tool_args,
            description=description,
        )
        decision = self._approval_callback(request)

        # Cache the decision
        self._memory.store(name, tool_args, decision)

        if not decision.approved:
            raise PermissionError(
                f"User denied {name}: {decision.note or 'no reason given'}"
            )
