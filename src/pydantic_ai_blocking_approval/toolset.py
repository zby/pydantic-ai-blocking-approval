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

    1. **pre_approved list**: Tools in this list skip approval.
       Tools NOT in the list require approval by default (secure by default).

    2. **needs_approval() method**: If the toolset implements this, it decides
       per-call whether approval is needed. Returns:
       - False: no approval needed
       - True: approval needed with default presentation
       - dict: approval needed with custom presentation (description, payload, etc.)

    3. **@requires_approval decorator**: Functions with this decorator always
       require approval, regardless of the list.

    Example:
        from pydantic_ai import Agent
        from pydantic_ai_blocking_approval import ApprovalToolset

        def cli_prompt(request: ApprovalRequest) -> ApprovalDecision:
            print(f"Approve {request.tool_name}? {request.description}")
            return ApprovalDecision(approved=input("[y/n]: ").lower() == "y")

        # Simple case: pre-approve safe tools, all others require approval
        approved_toolset = ApprovalToolset(
            inner=my_toolset,
            prompt_fn=cli_prompt,
            pre_approved=["get_time", "list_files"],
        )

        # Complex case: toolset decides per-call via needs_approval()
        approved_sandbox = ApprovalToolset(
            inner=file_sandbox,
            prompt_fn=cli_prompt,
            pre_approved=["read_file"],  # writes still require approval
        )
    """

    def __init__(
        self,
        inner: AbstractToolset,
        prompt_fn: Callable[[ApprovalRequest], ApprovalDecision],
        memory: Optional[ApprovalMemory] = None,
        pre_approved: Optional[list[str]] = None,
    ):
        """Initialize the approval wrapper.

        Args:
            inner: The toolset to wrap (must implement AbstractToolset)
            prompt_fn: Callback to prompt user for approval (blocks until decision)
            memory: Session cache for "approve for session" (created if None)
            pre_approved: List of tool names that skip approval entirely.
                Tools not in this list require approval by default (secure by default).
        """
        self._inner = inner
        self._prompt_fn = prompt_fn
        self._memory = memory or ApprovalMemory()
        self._pre_approved = set(pre_approved) if pre_approved else set()

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
        2. Check pre_approved list - if tool is in list, skip approval
        3. If toolset has needs_approval(), call it:
           - False: skip approval
           - True: prompt with default presentation
           - dict: prompt with custom presentation
        4. Otherwise, prompt for approval (secure by default)

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

        # Check if tool is in the pre_approved list
        if name in self._pre_approved:
            # Pre-approved, no approval needed
            return await self._inner.call_tool(name, tool_args, ctx, tool)

        # Tool is not pre-approved - check if toolset wants to decide
        presentation: dict[str, Any] = {}
        if hasattr(self._inner, "needs_approval"):
            try:
                result = self._inner.needs_approval(name, tool_args)
            except PermissionError:
                # Tool blocked entirely (e.g., path outside sandbox)
                raise

            if result is False:
                # Toolset says no approval needed for this specific call
                return await self._inner.call_tool(name, tool_args, ctx, tool)

            if isinstance(result, dict):
                # Toolset provided custom presentation
                presentation = result

        # Approval is needed - prompt user
        self._prompt_for_approval(name, tool_args, presentation)
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

    def _prompt_for_approval(
        self,
        name: str,
        tool_args: dict[str, Any],
        presentation: Optional[dict[str, Any]] = None,
    ) -> None:
        """Prompt user for approval, raising PermissionError if denied.

        Args:
            name: Tool name
            tool_args: Tool arguments
            presentation: Optional custom presentation dict with description,
                payload, and/or presentation keys
        """
        if presentation is None:
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
