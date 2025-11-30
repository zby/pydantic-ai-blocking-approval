"""Session memory for approval caching.

This module provides ApprovalMemory, which caches approval decisions
within a session to avoid repeatedly prompting for identical operations.
"""
from __future__ import annotations

import json
from typing import Optional

from .types import ApprovalDecision


class ApprovalMemory:
    """Session cache to avoid re-prompting for identical calls.

    When a user approves an operation with remember="session", subsequent
    identical requests (same tool_name + tool_args) will be auto-approved
    without prompting.

    The cache key is (tool_name, JSON-serialized tool_args).

    Example:
        memory = ApprovalMemory()

        # Store an approval
        decision = ApprovalDecision(approved=True, remember="session")
        memory.store("write_file", {"path": "/tmp/test.txt"}, decision)

        # Later lookup
        cached = memory.lookup("write_file", {"path": "/tmp/test.txt"})
        if cached and cached.approved:
            # Skip prompting, use cached approval
            ...
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], ApprovalDecision] = {}

    def lookup(self, tool_name: str, args: dict) -> Optional[ApprovalDecision]:
        """Look up a previous approval decision.

        Args:
            tool_name: Name of the tool
            args: Tool arguments (will be JSON-serialized for matching)

        Returns:
            Cached ApprovalDecision if found, None otherwise
        """
        key = self._make_key(tool_name, args)
        return self._cache.get(key)

    def store(self, tool_name: str, args: dict, decision: ApprovalDecision) -> None:
        """Store an approval decision for session reuse.

        Only stores if decision.remember == "session". Decisions with
        remember="none" are not cached.

        Args:
            tool_name: Name of the tool
            args: Tool arguments (will be JSON-serialized for matching)
            decision: The approval decision to cache
        """
        if decision.remember == "none":
            return
        key = self._make_key(tool_name, args)
        self._cache[key] = decision

    def clear(self) -> None:
        """Clear all session approvals."""
        self._cache.clear()

    def list_approvals(self) -> list[tuple[str, dict, ApprovalDecision]]:
        """List all cached session approvals.

        Returns:
            List of (tool_name, tool_args, decision) tuples for all cached approvals.
        """
        result = []
        for (tool_name, args_json), decision in self._cache.items():
            tool_args = json.loads(args_json)
            result.append((tool_name, tool_args, decision))
        return result

    def __len__(self) -> int:
        """Return the number of cached approvals."""
        return len(self._cache)

    @staticmethod
    def _make_key(tool_name: str, args: dict) -> tuple[str, str]:
        """Create hashable key for session matching."""
        return (tool_name, json.dumps(args, sort_keys=True, default=str))
