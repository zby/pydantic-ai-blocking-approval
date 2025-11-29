"""Integration tests with PydanticAI Agent and TestModel."""
import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from pydantic_ai_blocking_approval import (
    ApprovalController,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalToolset,
    requires_approval,
)


class TestApprovalIntegration:
    """Integration tests for approval flow with real agent."""

    def test_tool_requires_approval_and_denied(self):
        """Test that a tool with @requires_approval raises PermissionError when denied."""
        approval_requests: list[ApprovalRequest] = []

        def deny_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=False, note="User denied")

        @requires_approval
        def delete_file(path: str) -> str:
            """Delete a file at the given path."""
            return f"Deleted {path}"

        # Create a FunctionToolset with our tool
        inner_toolset = FunctionToolset([delete_file])

        # Wrap with approval
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            prompt_fn=deny_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        # Configure TestModel to call the delete_file tool
        # When approval is denied, PermissionError should be raised
        with pytest.raises(PermissionError) as exc_info:
            asyncio.run(
                agent.run(
                    "Delete the file /tmp/test.txt",
                    model=TestModel(call_tools=["delete_file"]),
                )
            )

        # The approval callback should have been called
        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "delete_file"

        # The exception message should contain the denial note
        assert "User denied" in str(exc_info.value)

    def test_tool_requires_approval_and_approved(self):
        """Test that a tool with @requires_approval executes when approved."""
        approval_requests: list[ApprovalRequest] = []

        def approve_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        @requires_approval
        def send_email(to: str, subject: str) -> str:
            """Send an email."""
            return f"Email sent to {to} with subject: {subject}"

        inner_toolset = FunctionToolset([send_email])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            prompt_fn=approve_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        # Configure TestModel to call the send_email tool
        result = asyncio.run(
            agent.run(
                "Send email to test@example.com about Meeting",
                model=TestModel(call_tools=["send_email"]),
            )
        )

        # The approval callback should have been called
        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "send_email"

        # The tool should have executed successfully
        assert "Email sent" in result.output or "success" in result.output.lower()

    def test_controller_approve_all_mode(self):
        """Test that approve_all mode auto-approves without prompting."""
        controller = ApprovalController(mode="approve_all")

        @requires_approval
        def dangerous_action() -> str:
            """Do something dangerous."""
            return "Action completed"

        inner_toolset = FunctionToolset([dangerous_action])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            prompt_fn=controller.approval_callback,
            memory=controller.memory,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        result = asyncio.run(
            agent.run(
                "Do the dangerous action",
                model=TestModel(call_tools=["dangerous_action"]),
            )
        )

        # Should succeed without any prompting
        assert "Action completed" in result.output or "success" in result.output.lower()

    def test_controller_strict_mode(self):
        """Test that strict mode auto-denies all requests with PermissionError."""
        controller = ApprovalController(mode="strict")

        @requires_approval
        def write_file(path: str, content: str) -> str:
            """Write content to a file."""
            return f"Wrote to {path}"

        inner_toolset = FunctionToolset([write_file])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            prompt_fn=controller.approval_callback,
            memory=controller.memory,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        # Strict mode should raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            asyncio.run(
                agent.run(
                    "Write 'hello' to /tmp/test.txt",
                    model=TestModel(call_tools=["write_file"]),
                )
            )

        # Should mention strict mode in the error
        assert "Strict mode" in str(exc_info.value)

    def test_tool_without_decorator_no_approval_needed(self):
        """Test that tools without @requires_approval execute without prompting."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        def safe_action(message: str) -> str:
            """A safe action that doesn't need approval."""
            return f"Processed: {message}"

        inner_toolset = FunctionToolset([safe_action])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            prompt_fn=should_not_be_called,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        result = asyncio.run(
            agent.run(
                "Process the message 'hello'",
                model=TestModel(call_tools=["safe_action"]),
            )
        )

        # Callback should NOT have been called
        assert not callback_called
        # Tool should have executed
        assert "Processed" in result.output or "hello" in result.output
