"""Tests for approval types."""
import pytest

from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalRequest,
    OperationDescriptor,
)


class TestOperationDescriptor:
    """Tests for OperationDescriptor."""

    def test_basic_descriptor(self):
        """Create a basic text operation descriptor."""
        descriptor = OperationDescriptor(
            type="text",
            content="Simple message",
        )
        assert descriptor.type == "text"
        assert descriptor.content == "Simple message"
        assert descriptor.language is None
        assert descriptor.metadata == {}

    def test_descriptor_with_language(self):
        """Create a descriptor with syntax highlighting hint."""
        descriptor = OperationDescriptor(
            type="file_content",
            content="def hello(): pass",
            language="python",
        )
        assert descriptor.language == "python"

    def test_descriptor_with_metadata(self):
        """Create a descriptor with metadata."""
        descriptor = OperationDescriptor(
            type="diff",
            content="- old\n+ new",
            metadata={"file": "test.py", "lines": 10},
        )
        assert descriptor.metadata["file"] == "test.py"


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def test_basic_request(self):
        """Create a basic approval request."""
        request = ApprovalRequest(
            tool_name="write_file",
            description="Write to /tmp/test.txt",
            payload={"path": "/tmp/test.txt"},
        )
        assert request.tool_name == "write_file"
        assert request.description == "Write to /tmp/test.txt"
        assert request.payload == {"path": "/tmp/test.txt"}
        assert request.operation is None

    def test_request_with_operation(self):
        """Create a request with operation descriptor."""
        operation = OperationDescriptor(type="text", content="Details")
        request = ApprovalRequest(
            tool_name="shell",
            description="Run command",
            payload={"command": "ls"},
            operation=operation,
        )
        assert request.operation is not None
        assert request.operation.type == "text"


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
