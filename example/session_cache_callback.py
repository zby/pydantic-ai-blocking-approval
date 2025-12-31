from __future__ import annotations

import json

from pydantic_ai.toolsets import FunctionToolset

from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
)


def prompt_user(request: ApprovalRequest) -> str:
    return input(
        f"Approve {request.tool_name}? [y]es / [n]o / [s]ession: "
    ).strip().lower()


def with_session_cache(prompt):
    cache: dict[tuple[str, str], ApprovalDecision] = {}

    def callback(request: ApprovalRequest) -> ApprovalDecision:
        key = (
            request.tool_name,
            json.dumps(request.tool_args, sort_keys=True, default=str),
        )
        cached = cache.get(key)
        if cached is not None:
            return cached

        response = prompt(request)
        if response == "s":
            decision = ApprovalDecision(approved=True, remember="session")
        elif response == "y":
            decision = ApprovalDecision(approved=True)
        else:
            decision = ApprovalDecision(approved=False, note="User denied")

        if decision.approved and decision.remember == "session":
            cache[key] = decision
        return decision

    return callback


def add(a: int, b: int) -> int:
    return a + b


inner_toolset = FunctionToolset([add])
approved_toolset = ApprovalToolset(
    inner=inner_toolset,
    approval_callback=with_session_cache(prompt_user),
)
