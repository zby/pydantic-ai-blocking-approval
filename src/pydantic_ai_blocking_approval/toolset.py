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

    Approval is determined by a layered approach:

    1. **require_approval list**: Tools in this list are candidates for approval.
       Tools NOT in the list skip approval entirely (unless decorated).

    2. **needs_approval() method**: If the toolset implements this, it decides
       per-call whether approval is actually needed (returns bool).

    3. **@requires_approval decorator**: Functions with this decorator always
       require approval, regardless of the list.

    Presentation can be customized via the optional present_for_approval() method.

    Example:
        from pydantic_ai import Agent
        from pydantic_ai_blocking_approval import ApprovalToolset

        def cli_prompt(request: ApprovalRequest) -> ApprovalDecision:
            print(f"Approve {request.tool_name}? {request.description}")
            return ApprovalDecision(approved=input("[y/n]: ").lower() == "y")

        # Simple case: always prompt for these tools
        approved_toolset = ApprovalToolset(
            inner=my_toolset,
            prompt_fn=cli_prompt,
            require_approval=["send_email", "delete_file"],
        )

        # Complex case: toolset decides per-call via needs_approval()
        approved_sandbox = ApprovalToolset(
            inner=file_sandbox,
            prompt_fn=cli_prompt,
            require_approval=["write_file", "read_file"],
        )
    """

    def __init__(
        self,
        inner: AbstractToolset,
        prompt_fn: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
        require_approval: Optional[list[str]] = None,
    ):
        """Initialize the approval wrapper.

        Args:
            inner: The toolset to wrap (must implement AbstractToolset)
            prompt_fn: Callback to prompt user for approval (blocks until decision)
            memory: Session cache for "approve for session" (created if None)
            require_approval: List of tool names that may require approval.
                If None, only @requires_approval decorated functions are checked.
        """
        self._inner = inner
        self._prompt_fn = prompt_fn
        self._memory = memory or ApprovalMemory()
        self._require_approval = set(require_approval) if require_approval else set()

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

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: Any,
        tool: Any,
    ) -> Any:
        """Intercept tool calls for approval.

        Approval flow:
        1. Check @requires_approval decorator - always prompt if present
        2. Check require_approval list - if tool not in list, skip approval
        3. If toolset has needs_approval(), call it - if False, skip approval
        4. Otherwise, prompt for approval

        Args:
            name: Tool name being called
            tool_args: Arguments passed to the tool
            ctx: PydanticAI run context
            tool: The tool object/function

        Returns:
            Result from the inner toolset's call_tool

        Raises:
            PermissionError: If user denies approval or toolset blocks operation
        """
        # Check for decorated functions with @requires_approval marker
        func = self._get_function(name, tool)
        if getattr(func, "_requires_approval", False):
            self._prompt_for_approval(name, tool_args)
            return await self._inner.call_tool(name, tool_args, ctx, tool)

        # Check if tool is in the require_approval list
        if name not in self._require_approval:
            # Not in list, no approval needed
            return await self._inner.call_tool(name, tool_args, ctx, tool)

        # Tool is in require_approval list - check if toolset wants to decide
        if hasattr(self._inner, "needs_approval"):
            try:
                needs = self._inner.needs_approval(name, tool_args)
            except PermissionError:
                # Tool blocked entirely (e.g., path outside sandbox)
                raise

            if not needs:
                # Toolset says no approval needed for this specific call
                return await self._inner.call_tool(name, tool_args, ctx, tool)

        # Approval is needed - prompt user
        self._prompt_for_approval(name, tool_args)
        return await self._inner.call_tool(name, tool_args, ctx, tool)

    def _get_function(self, name: str, tool: Any) -> Any:
        """Extract the underlying function from a tool."""
        func = None
        if hasattr(self._inner, "tools") and name in self._inner.tools:
            inner_tool = self._inner.tools[name]
            func = getattr(inner_tool, "function", None)
        if func is None:
            func = getattr(tool, "function", tool)
        return func

    def _prompt_for_approval(self, name: str, tool_args: dict[str, Any]) -> None:
        """Prompt user for approval, raising PermissionError if denied.

        Uses present_for_approval() from toolset if available for custom presentation,
        otherwise uses default presentation (tool name + args).
        """
        # Get presentation info
        if hasattr(self._inner, "present_for_approval"):
            try:
                presentation = self._inner.present_for_approval(name, tool_args)
            except Exception:
                presentation = {}
        else:
            presentation = {}

        description = presentation.get(
            "description",
            f"{name}({', '.join(f'{k}={v!r}' for k, v in tool_args.items())})",
        )
        payload = presentation.get("payload", tool_args)
        extra_presentation = presentation.get("presentation")

        # Check session cache first
        cached = self._memory.lookup(name, payload)
        if cached is not None and cached.approved:
            return  # Already approved in session

        # Build request and prompt user
        request = ApprovalRequest(
            tool_name=name,
            description=description,
            payload=payload,
            presentation=extra_presentation,
        )
        decision = self._prompt_fn(request)

        # Cache the decision
        self._memory.store(name, payload, decision)

        if not decision.approved:
            raise PermissionError(
                f"User denied {name}: {decision.note or 'no reason given'}"
            )
