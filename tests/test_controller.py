"""Tests for ApprovalController."""
import pytest

from pydantic_ai_blocking_approval import (
    ApprovalController,
    ApprovalDecision,
    ApprovalRequest,
)


class TestApprovalController:
    """Tests for the ApprovalController class."""

    def test_approve_all_mode(self):
        """approve_all mode auto-approves all requests."""
        controller = ApprovalController(mode="approve_all")
        request = ApprovalRequest(
            tool_name="dangerous_tool",
            tool_args={"action": "destroy"},
            description="Do something dangerous",
        )

        decision = controller.request_approval_sync(request)

        assert decision.approved is True

    def test_strict_mode(self):
        """strict mode auto-denies all requests."""
        controller = ApprovalController(mode="strict")
        request = ApprovalRequest(
            tool_name="any_tool",
            tool_args={"key": "value"},
            description="Any operation",
        )

        decision = controller.request_approval_sync(request)

        assert decision.approved is False
        assert "Strict mode" in decision.note

    def test_session_approval_caching(self):
        """Session approval caches approved requests."""
        approvals = []

        def callback(request: ApprovalRequest) -> ApprovalDecision:
            approvals.append(request)
            return ApprovalDecision(approved=True, remember="session")

        controller = ApprovalController(mode="interactive", approval_callback=callback)
        request = ApprovalRequest(
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            description="Write to file",
        )

        # First call - should invoke callback
        decision1 = controller.request_approval_sync(request)
        assert decision1.approved is True
        assert len(approvals) == 1

        # Second identical call - should use cache
        decision2 = controller.request_approval_sync(request)
        assert decision2.approved is True
        assert len(approvals) == 1  # Callback not called again

    def test_session_approval_different_payloads(self):
        """Different payloads require separate approvals."""
        approvals = []

        def callback(request: ApprovalRequest) -> ApprovalDecision:
            approvals.append(request)
            return ApprovalDecision(approved=True, remember="session")

        controller = ApprovalController(mode="interactive", approval_callback=callback)

        request1 = ApprovalRequest(
            tool_name="write_file",
            tool_args={"path": "/tmp/file1.txt"},
            description="Write file 1",
        )
        request2 = ApprovalRequest(
            tool_name="write_file",
            tool_args={"path": "/tmp/file2.txt"},
            description="Write file 2",
        )

        controller.request_approval_sync(request1)
        controller.request_approval_sync(request2)

        # Both should trigger callback (different tool_args)
        assert len(approvals) == 2

    def test_session_approval_remember_none_not_cached(self):
        """remember='none' approvals are not cached."""
        approvals = []

        def callback(request: ApprovalRequest) -> ApprovalDecision:
            approvals.append(request)
            return ApprovalDecision(approved=True, remember="none")

        controller = ApprovalController(mode="interactive", approval_callback=callback)
        request = ApprovalRequest(
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            description="Write to file",
        )

        controller.request_approval_sync(request)
        controller.request_approval_sync(request)

        # Both calls should trigger callback (remember='none' doesn't cache)
        assert len(approvals) == 2

    def test_clear_session_approvals(self):
        """clear_session_approvals removes all cached approvals."""

        def callback(request: ApprovalRequest) -> ApprovalDecision:
            return ApprovalDecision(approved=True, remember="session")

        controller = ApprovalController(mode="interactive", approval_callback=callback)
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={"key": "value"},
            description="Test",
        )

        controller.request_approval_sync(request)
        assert controller.is_session_approved(request) is True

        controller.clear_session_approvals()
        assert controller.is_session_approved(request) is False

    def test_interactive_mode_without_callback_raises(self):
        """Interactive mode without callback raises NotImplementedError."""
        controller = ApprovalController(mode="interactive")
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={"key": "value"},
            description="Test",
        )

        with pytest.raises(NotImplementedError, match="No approval_callback"):
            controller.request_approval_sync(request)

    def test_approval_callback_property_approve_all(self):
        """approval_callback property returns auto-approve for approve_all mode."""
        controller = ApprovalController(mode="approve_all")
        callback = controller.approval_callback

        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )
        decision = callback(request)

        assert decision.approved is True

    def test_approval_callback_property_strict(self):
        """approval_callback property returns auto-deny for strict mode."""
        controller = ApprovalController(mode="strict")
        callback = controller.approval_callback

        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )
        decision = callback(request)

        assert decision.approved is False

    def test_approval_callback_property_interactive_no_callback_raises(self):
        """approval_callback property raises for interactive mode without callback."""
        controller = ApprovalController(mode="interactive")

        with pytest.raises(RuntimeError, match="No approval_callback set"):
            _ = controller.approval_callback

    def test_request_approval_sync_with_async_callback_raises(self):
        """request_approval_sync raises TypeError if callback is async."""

        async def async_callback(request: ApprovalRequest) -> ApprovalDecision:
            return ApprovalDecision(approved=True)

        controller = ApprovalController(
            mode="interactive",
            approval_callback=async_callback,
        )
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )

        with pytest.raises(TypeError, match="requires a sync callback"):
            controller.request_approval_sync(request)

    def test_request_approval_without_callback_raises(self):
        """request_approval (async) raises RuntimeError if no callback."""
        import asyncio

        controller = ApprovalController(mode="interactive")
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )

        async def test_async():
            with pytest.raises(RuntimeError, match="No approval_callback"):
                await controller.request_approval(request)

        asyncio.run(test_async())

    def test_callback_exception_propagates_sync(self):
        """Callback exceptions propagate through request_approval_sync."""

        def failing_callback(request: ApprovalRequest) -> ApprovalDecision:
            raise ValueError("Approval service unavailable")

        controller = ApprovalController(
            mode="interactive",
            approval_callback=failing_callback,
        )
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )

        with pytest.raises(ValueError, match="Approval service unavailable"):
            controller.request_approval_sync(request)

    def test_callback_exception_propagates_async(self):
        """Callback exceptions propagate through request_approval (async)."""
        import asyncio

        async def failing_callback(request: ApprovalRequest) -> ApprovalDecision:
            raise ConnectionError("Lost connection to approval server")

        controller = ApprovalController(
            mode="interactive",
            approval_callback=failing_callback,
        )
        request = ApprovalRequest(
            tool_name="tool",
            tool_args={},
            description="Test",
        )

        async def test_async():
            with pytest.raises(ConnectionError, match="Lost connection"):
                await controller.request_approval(request)

        asyncio.run(test_async())
