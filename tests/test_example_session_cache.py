"""Tests for the session cache example."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic_ai_blocking_approval import ApprovalRequest


def load_example_module():
    path = Path(__file__).resolve().parents[1] / "example" / "session_cache_callback.py"
    spec = importlib.util.spec_from_file_location("session_cache_callback", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Failed to load session_cache_callback example")
    spec.loader.exec_module(module)
    return module


def test_session_cache_approve_for_session():
    module = load_example_module()
    calls = 0

    def prompt(_: ApprovalRequest) -> str:
        nonlocal calls
        calls += 1
        return "s"

    callback = module.with_session_cache(prompt)
    request = ApprovalRequest(
        tool_name="add",
        tool_args={"a": 1, "b": 2},
        description="Add two numbers",
    )

    first = callback(request)
    second = callback(request)
    assert first.approved is True
    assert first.remember == "session"
    assert second.approved is True
    assert second.remember == "session"
    assert calls == 1


def test_session_cache_approve_once_not_cached():
    module = load_example_module()
    calls = 0

    def prompt(_: ApprovalRequest) -> str:
        nonlocal calls
        calls += 1
        return "y"

    callback = module.with_session_cache(prompt)
    request = ApprovalRequest(
        tool_name="add",
        tool_args={"a": 1, "b": 2},
        description="Add two numbers",
    )

    first = callback(request)
    second = callback(request)
    assert first.approved is True
    assert first.remember == "none"
    assert second.approved is True
    assert second.remember == "none"
    assert calls == 2


def test_session_cache_denied():
    module = load_example_module()
    calls = 0

    def prompt(_: ApprovalRequest) -> str:
        nonlocal calls
        calls += 1
        return "n"

    callback = module.with_session_cache(prompt)
    request = ApprovalRequest(
        tool_name="add",
        tool_args={"a": 1, "b": 2},
        description="Add two numbers",
    )

    decision = callback(request)
    assert decision.approved is False
    assert decision.note == "User denied"
    assert calls == 1
