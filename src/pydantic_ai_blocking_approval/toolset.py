"""Approval toolset wrappers for PydanticAI toolsets.

This module provides approval wrappers that intercept tool calls for approval checking:

- BaseApprovalToolset: Abstract base with shared approval machinery
- SimpleApprovalToolset: Config-based approval (for simple inner toolsets)
- ApprovalToolset: Delegates to inner.needs_approval() (for smart inner toolsets)
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable, Optional

from pydantic_ai.toolsets import AbstractToolset

from .memory import ApprovalMemory
from .types import ApprovalDecision, ApprovalRequest


class BaseApprovalToolset(AbstractToolset):
    """Abstract base class with shared approval machinery.

    Subclasses must implement `needs_approval()` to determine when approval is needed.

    This base class handles:
    - Wrapping an inner toolset
    - Intercepting tool calls via `call_tool()`
    - Prompting for approval via callback
    - Session caching of approval decisions
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
                a dict of settings. Subclasses define how config is used.
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

    @abstractmethod
    def needs_approval(self, name: str, tool_args: dict[str, Any]) -> bool | dict:
        """Determine if this tool call needs approval.

        Subclasses must implement this method.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool

        Returns:
            False: no approval needed
            True: approval needed with default description
            dict: approval needed with custom description ({"description": "..."})
        """
        ...

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


class SimpleApprovalToolset(BaseApprovalToolset):
    """Config-based approval wrapper.

    Uses the `config` dict to determine which tools are pre-approved.
    Tools not configured as pre_approved require approval (secure by default).

    Use this for simple inner toolsets that don't implement their own
    `needs_approval()` method.

    Example:
        from pydantic_ai_blocking_approval import SimpleApprovalToolset

        approved = SimpleApprovalToolset(
            inner=my_toolset,
            approval_callback=my_callback,
            config={
                "get_time": {"pre_approved": True},
                "list_files": {"pre_approved": True},
                # All other tools require approval
            },
        )
    """

    def needs_approval(self, name: str, tool_args: dict[str, Any]) -> bool | dict:
        """Check config for pre_approved status.

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool (unused in this implementation)

        Returns:
            False if tool is pre_approved in config, True otherwise
        """
        tool_config = self.config.get(name, {})
        if tool_config.get("pre_approved"):
            return False
        return True  # Secure by default


class ApprovalToolset(BaseApprovalToolset):
    """Delegating approval wrapper.

    Delegates `needs_approval()` to the inner toolset, which must implement it.
    Use this for smart inner toolsets that have their own approval logic.

    Example:
        from pydantic_ai_blocking_approval import ApprovalToolset

        class MyToolset(AbstractToolset):
            def needs_approval(self, name: str, tool_args: dict) -> bool | dict:
                if name == "safe_tool":
                    return False
                return {"description": f"Run {name}"}

        approved = ApprovalToolset(
            inner=MyToolset(),
            approval_callback=my_callback,
        )
    """

    def needs_approval(self, name: str, tool_args: dict[str, Any]) -> bool | dict:
        """Delegate to inner toolset's needs_approval().

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool

        Returns:
            Result from inner toolset's needs_approval()

        Raises:
            AttributeError: If inner toolset doesn't have needs_approval()
        """
        return self._inner.needs_approval(name, tool_args)
