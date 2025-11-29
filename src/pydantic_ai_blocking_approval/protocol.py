"""Protocol for approval-aware toolsets.

This module defines protocols that toolsets can implement
to provide custom approval logic.
"""
from __future__ import annotations

from typing import Any, Protocol


class ApprovalConfigurable(Protocol):
    """Protocol for toolsets that can control approval decisions.

    Toolsets implementing this protocol can decide per-call whether
    approval is needed, and optionally customize the presentation.

    The ApprovalToolset checks for these methods:

    1. needs_approval(tool_name, args) -> bool
       Returns True if this specific call needs approval.

    2. present_for_approval(tool_name, args) -> dict  (optional)
       Returns custom presentation info for the approval prompt.

    Example:
        class ShellToolset:
            def needs_approval(self, tool_name: str, args: dict) -> bool:
                if tool_name == "shell_exec":
                    return self._is_dangerous_command(args["command"])
                return False

            def present_for_approval(self, tool_name: str, args: dict) -> dict:
                return {
                    "description": f"Execute: {args['command'][:50]}...",
                    "payload": {"command_hash": hash(args["command"])},
                }
    """

    def needs_approval(
        self, tool_name: str, args: dict[str, Any]
    ) -> bool:
        """Return True if this specific call needs approval.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments

        Returns:
            True if approval is needed, False otherwise

        Raises:
            PermissionError: If operation is blocked entirely
                (e.g., path outside sandbox)
        """
        ...


class PresentableForApproval(Protocol):
    """Optional protocol for customizing approval presentation.

    Toolsets can implement this to provide custom descriptions
    and payload for the approval prompt.
    """

    def present_for_approval(
        self, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Return presentation info for the approval prompt.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments

        Returns:
            dict with optional keys:
                - description: str - Human-readable description
                - payload: dict - Data for session pattern matching
                - presentation: dict - Rich display data (diffs, etc.)
        """
        ...
