"""Tests for approval types."""

from dataclasses import FrozenInstanceError

import pytest

from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResult,
    needs_approval_from_config,
)


class TestApprovalResult:
    """Tests for ApprovalResult."""

    def test_blocked_factory(self):
        """Test ApprovalResult.blocked() factory method."""
        result = ApprovalResult.blocked("Operation not allowed")
        assert result.status == "blocked"
        assert result.block_reason == "Operation not allowed"
        assert result.is_blocked is True
        assert result.is_pre_approved is False
        assert result.is_needs_approval is False

    def test_pre_approved_factory(self):
        """Test ApprovalResult.pre_approved() factory method."""
        result = ApprovalResult.pre_approved()
        assert result.status == "pre_approved"
        assert result.block_reason is None
        assert result.is_blocked is False
        assert result.is_pre_approved is True
        assert result.is_needs_approval is False

    def test_needs_approval_factory(self):
        """Test ApprovalResult.needs_approval() factory method."""
        result = ApprovalResult.needs_approval()
        assert result.status == "needs_approval"
        assert result.block_reason is None
        assert result.is_blocked is False
        assert result.is_pre_approved is False
        assert result.is_needs_approval is True

    def test_frozen_dataclass(self):
        """Test that ApprovalResult is immutable."""
        result = ApprovalResult.blocked("reason")
        with pytest.raises(FrozenInstanceError):
            result.status = "pre_approved"  # type: ignore


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def test_basic_request(self):
        """Create a basic approval request."""
        request = ApprovalRequest(
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            description="Write to /tmp/test.txt",
        )
        assert request.tool_name == "write_file"
        assert request.tool_args == {"path": "/tmp/test.txt"}
        assert request.description == "Write to /tmp/test.txt"

    def test_request_with_complex_args(self):
        """Create a request with complex tool arguments."""
        request = ApprovalRequest(
            tool_name="patch_file",
            tool_args={
                "path": "config.json",
                "diff": "- old\n+ new",
                "lines_changed": 5,
            },
            description="Update config.json",
        )
        assert request.tool_name == "patch_file"
        assert request.tool_args["diff"] == "- old\n+ new"


class TestApprovalDecision:
    """Tests for ApprovalDecision."""

    def test_approved_once(self):
        """Create an approved-once decision."""
        decision = ApprovalDecision(approved=True)
        assert decision.approved is True
        assert decision.remember == "none"
        assert decision.note is None

    def test_approved_session(self):
        """Create an approved-for-session decision."""
        decision = ApprovalDecision(approved=True, remember="session")
        assert decision.approved is True
        assert decision.remember == "session"

    def test_denied_with_note(self):
        """Create a denied decision with a note."""
        decision = ApprovalDecision(
            approved=False,
            note="Not safe to execute",
        )
        assert decision.approved is False
        assert decision.note == "Not safe to execute"


class TestNeedsApprovalFromConfig:
    """Tests for needs_approval_from_config helper."""

    def test_pre_approved_from_config(self):
        config = {"safe_tool": {"pre_approved": True}}
        result = needs_approval_from_config("safe_tool", config)
        assert result.is_pre_approved

    def test_default_needs_approval(self):
        result = needs_approval_from_config("unknown_tool", {})
        assert result.is_needs_approval
