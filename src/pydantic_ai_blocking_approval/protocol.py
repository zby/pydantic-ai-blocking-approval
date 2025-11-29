"""Protocol for approval-aware toolsets.

This module defines the protocol that toolsets can implement
to provide custom approval logic.
"""
from __future__ import annotations

from typing import Any, Protocol, Union


class ApprovalConfigurable(Protocol):
    """Protocol for toolsets that control approval decisions.

    Toolsets implementing this protocol decide per-call whether
    approval is needed and can optionally customize the presentation.

    The ApprovalToolset checks for this method:

    needs_approval(tool_name, args) -> bool | dict
        - False: No approval needed, proceed immediately
        - True: Approval needed, use default presentation
        - dict: Approval needed, with custom presentation

    The dict can contain:
        - description: str - Human-readable description for the prompt
        - payload: dict - Data for session cache matching (controls granularity)
        - presentation: dict - Rich display data (diffs, syntax highlighting, etc.)

    Example:
        class ShellToolset:
            def needs_approval(self, tool_name: str, args: dict) -> bool | dict:
                if tool_name != "shell_exec":
                    return False

                command = args["command"]
                if self._is_safe_command(command):
                    return False

                # Dangerous command - require approval with custom presentation
                return {
                    "description": f"Execute: {command[:50]}...",
                    "payload": {"command": command},
                }

    Raising PermissionError blocks the operation entirely (e.g., path outside sandbox).
    """

    def needs_approval(
        self, tool_name: str, args: dict[str, Any]
    ) -> Union[bool, dict[str, Any]]:
        """Decide if this specific call needs approval.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments

        Returns:
            - False: No approval needed
            - True: Approval needed with default presentation
            - dict: Approval needed with custom presentation containing
              optional keys: description, payload, presentation

        Raises:
            PermissionError: If operation is blocked entirely
        """
        ...
