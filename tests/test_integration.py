"""Integration tests with PydanticAI Agent and TestModel."""
import asyncio
import re
from typing import Any

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.toolsets.abstract import AbstractToolset

from pydantic_ai_blocking_approval import (
    ApprovalController,
    ApprovalDecision,
    ApprovalMemory,
    ApprovalRequest,
    ApprovalResult,
    ApprovalToolset,
)


# Mock context for testing needs_approval directly
MOCK_CTX: Any = None  # Tests that call needs_approval directly can pass None


class TestApprovalIntegration:
    """Integration tests for approval flow with real agent."""

    def test_tool_requires_approval_and_denied(self):
        """Test that a tool requires approval by default and raises PermissionError when denied."""
        approval_requests: list[ApprovalRequest] = []

        def deny_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=False, note="User denied")

        def delete_file(path: str) -> str:
            """Delete a file at the given path."""
            return f"Deleted {path}"

        # Create a FunctionToolset with our tool
        inner_toolset = FunctionToolset([delete_file])

        # Wrap with approval (no config = requires approval by default)
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=deny_callback,
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
        """Test that a tool executes when approved."""
        approval_requests: list[ApprovalRequest] = []

        def approve_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        def send_email(to: str, subject: str) -> str:
            """Send an email."""
            return f"Email sent to {to} with subject: {subject}"

        inner_toolset = FunctionToolset([send_email])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=approve_callback,
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

        def dangerous_action() -> str:
            """Do something dangerous."""
            return "Action completed"

        inner_toolset = FunctionToolset([dangerous_action])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=controller.approval_callback,
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

        def write_file(path: str, content: str) -> str:
            """Write content to a file."""
            return f"Wrote to {path}"

        inner_toolset = FunctionToolset([write_file])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=controller.approval_callback,
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

    def test_tool_without_config_requires_approval(self):
        """Test that tools without config require approval by default (secure by default)."""
        approval_requests: list[ApprovalRequest] = []

        def approve_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        def some_action(message: str) -> str:
            """An action that requires approval by default."""
            return f"Processed: {message}"

        inner_toolset = FunctionToolset([some_action])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=approve_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        result = asyncio.run(
            agent.run(
                "Process the message 'hello'",
                model=TestModel(call_tools=["some_action"]),
            )
        )

        # Callback SHOULD have been called (secure by default)
        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "some_action"
        # Tool should have executed after approval
        assert "Processed" in result.output or "hello" in result.output

    def test_pre_approved_tool_skips_approval(self):
        """Test that tools with pre_approved=True in config execute without prompting."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        def safe_action(message: str) -> str:
            """A safe action that is pre-approved."""
            return f"Processed: {message}"

        inner_toolset = FunctionToolset([safe_action])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=should_not_be_called,
            config={"safe_action": {"pre_approved": True}},
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

        # Callback should NOT have been called (pre-approved)
        assert not callback_called
        # Tool should have executed
        assert "Processed" in result.output or "hello" in result.output


class ShellToolset(AbstractToolset):
    """Shell toolset with custom needs_approval logic.

    Demonstrates how to implement SupportsNeedsApproval protocol
    for custom approval logic based on command patterns.
    """

    # Commands that are always safe (read-only, no side effects)
    SAFE_COMMANDS = {"ls", "pwd", "whoami", "date", "echo", "cat", "head", "tail"}

    # Patterns that are always dangerous
    DANGEROUS_PATTERNS = [
        r"\brm\b",  # rm command
        r"\bsudo\b",  # sudo
        r"\bmv\b",  # mv command
        r"\bchmod\b",  # chmod
        r"\bchown\b",  # chown
        r"[|>&]",  # pipes and redirects
        r"\$\(",  # command substitution
        r"`",  # backticks
        r";\s*\w",  # command chaining
    ]

    # Paths that are safe to read
    SAFE_READ_PATHS = {"/tmp", "/var/log", "."}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._executed_commands: list[str] = []
        self.config = config or {}
        self._last_description: str | None = None

    @property
    def id(self) -> str | None:
        return "shell_toolset"

    async def get_tools(self, ctx: Any) -> dict:
        """Return available tools."""
        return {
            "shell_exec": {
                "description": "Execute a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"},
                    },
                    "required": ["command"],
                },
            }
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: Any, tool: Any
    ) -> str:
        """Execute the tool (mock implementation)."""
        if name == "shell_exec":
            command = tool_args.get("command", "")
            self._executed_commands.append(command)
            return f"Executed: {command}"
        raise ValueError(f"Unknown tool: {name}")

    def needs_approval(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any] | None = None
    ) -> ApprovalResult:
        """Decide if shell command needs approval based on patterns.

        Implements SupportsNeedsApproval protocol.
        ctx can be None for testing purposes.
        """
        # ctx is available for user-specific logic (e.g., ctx.deps)
        tool_config = self.config.get(name, {})

        # Check pre_approved first
        if tool_config.get("pre_approved"):
            return ApprovalResult.pre_approved()

        if name != "shell_exec":
            return ApprovalResult.needs_approval()

        command = tool_args.get("command", "")

        # Check for dangerous patterns first (highest priority)
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                self._last_description = (
                    f"Execute potentially dangerous command: {command}"
                )
                return ApprovalResult.needs_approval()

        # Check if it's a safe command
        base_command = command.split()[0] if command.split() else ""
        safe_commands = tool_config.get("safe_commands", self.SAFE_COMMANDS)
        if base_command in safe_commands:
            # Additional check for cat/head/tail - verify path is safe
            if base_command in {"cat", "head", "tail"} and len(command.split()) > 1:
                path = command.split()[1]
                safe_paths = tool_config.get("safe_read_paths", self.SAFE_READ_PATHS)
                if not any(path.startswith(safe) for safe in safe_paths):
                    self._last_description = f"Read file outside safe paths: {path}"
                    return ApprovalResult.needs_approval()
            return ApprovalResult.pre_approved()

        # Unknown command - require approval
        self._last_description = f"Execute command: {command}"
        return ApprovalResult.needs_approval()

    def get_approval_description(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any] | None = None
    ) -> str:
        """Return description for approval prompt."""
        if self._last_description:
            return self._last_description
        command = tool_args.get("command", "")
        return f"Execute: {command}"


class TestShellToolsetWithApproval:
    """Tests for ShellToolset with SupportsNeedsApproval and ApprovalToolset wrapper."""

    def test_needs_approval_safe_commands(self):
        """Test that safe commands return pre_approved from needs_approval."""
        toolset = ShellToolset()

        # Safe commands should return pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "ls -la"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "pwd"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "whoami"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "date"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "echo hello"}).is_pre_approved

    def test_needs_approval_dangerous_patterns(self):
        """Test that dangerous patterns return needs_approval with custom description."""
        toolset = ShellToolset()

        # rm command
        result = toolset.needs_approval("shell_exec", {"command": "rm -rf /tmp/files"})
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "rm -rf /tmp/files"})
        assert "dangerous" in desc.lower()
        assert "rm -rf /tmp/files" in desc

        # sudo command
        result = toolset.needs_approval("shell_exec", {"command": "sudo apt update"})
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "sudo apt update"})
        assert "dangerous" in desc.lower()

        # pipe
        result = toolset.needs_approval("shell_exec", {"command": "ls | grep foo"})
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "ls | grep foo"})
        assert "dangerous" in desc.lower()

        # redirect
        result = toolset.needs_approval("shell_exec", {"command": "echo x > file"})
        assert result.is_needs_approval

        # command substitution
        result = toolset.needs_approval("shell_exec", {"command": "echo $(whoami)"})
        assert result.is_needs_approval

    def test_needs_approval_cat_safe_paths(self):
        """Test that cat on safe paths doesn't require approval."""
        toolset = ShellToolset()

        # Safe paths
        assert toolset.needs_approval("shell_exec", {"command": "cat /tmp/test.log"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "cat /var/log/syslog"}).is_pre_approved
        assert toolset.needs_approval("shell_exec", {"command": "cat ./local.txt"}).is_pre_approved

    def test_needs_approval_cat_unsafe_paths(self):
        """Test that cat on sensitive paths requires approval."""
        toolset = ShellToolset()

        # Unsafe paths
        result = toolset.needs_approval("shell_exec", {"command": "cat /etc/passwd"})
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "cat /etc/passwd"})
        assert "/etc/passwd" in desc

        result = toolset.needs_approval("shell_exec", {"command": "cat /home/user/.ssh/id_rsa"})
        assert result.is_needs_approval

    def test_needs_approval_unknown_commands(self):
        """Test that unknown commands require approval with description."""
        toolset = ShellToolset()

        result = toolset.needs_approval("shell_exec", {"command": "mycustomtool --flag"})
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "mycustomtool --flag"})
        assert "mycustomtool" in desc

    def test_approval_toolset_skips_safe_command(self):
        """Test ApprovalToolset with ShellToolset skips approval for safe commands."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        shell_toolset = ShellToolset()
        approved_toolset = ApprovalToolset(
            inner=shell_toolset,
            approval_callback=should_not_be_called,
        )

        # Call tool directly (bypassing agent)
        result = asyncio.run(
            approved_toolset.call_tool(
                "shell_exec",
                {"command": "ls -la"},
                ctx=None,
                tool=None,
            )
        )

        assert not callback_called
        assert "ls -la" in shell_toolset._executed_commands
        assert "Executed: ls -la" in result

    def test_approval_toolset_prompts_for_dangerous_command(self):
        """Test ApprovalToolset with ShellToolset prompts for dangerous commands."""
        approval_requests: list[ApprovalRequest] = []

        def approve_callback(request: ApprovalRequest) -> ApprovalDecision:
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        shell_toolset = ShellToolset()
        approved_toolset = ApprovalToolset(
            inner=shell_toolset,
            approval_callback=approve_callback,
        )

        result = asyncio.run(
            approved_toolset.call_tool(
                "shell_exec",
                {"command": "rm -rf /tmp/old_files"},
                ctx=None,
                tool=None,
            )
        )

        assert len(approval_requests) == 1
        req = approval_requests[0]
        assert req.tool_name == "shell_exec"
        assert "dangerous" in req.description.lower()
        assert req.tool_args["command"] == "rm -rf /tmp/old_files"
        assert "rm -rf /tmp/old_files" in shell_toolset._executed_commands

    def test_approval_toolset_denies_command(self):
        """Test ApprovalToolset raises PermissionError when denied."""
        shell_toolset = ShellToolset()
        approved_toolset = ApprovalToolset(
            inner=shell_toolset,
            approval_callback=lambda req: ApprovalDecision(
                approved=False, note="Too dangerous"
            ),
        )

        with pytest.raises(PermissionError) as exc_info:
            asyncio.run(
                approved_toolset.call_tool(
                    "shell_exec",
                    {"command": "sudo rm -rf /"},
                    ctx=None,
                    tool=None,
                )
            )

        assert "Too dangerous" in str(exc_info.value)
        assert len(shell_toolset._executed_commands) == 0  # Never executed

    def test_session_caching_for_commands(self):
        """Test session approval caching works with command-based args."""
        approval_count = 0
        memory = ApprovalMemory()

        def approve_for_session(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal approval_count
            approval_count += 1
            return ApprovalDecision(approved=True, remember="session")

        shell_toolset = ShellToolset()
        approved_toolset = ApprovalToolset(
            inner=shell_toolset,
            approval_callback=approve_for_session,
            memory=memory,
        )

        # First call - should prompt
        asyncio.run(
            approved_toolset.call_tool(
                "shell_exec",
                {"command": "rm /tmp/file1.txt"},
                ctx=None,
                tool=None,
            )
        )
        assert approval_count == 1

        # Second call with same command - should use cached approval
        asyncio.run(
            approved_toolset.call_tool(
                "shell_exec",
                {"command": "rm /tmp/file1.txt"},
                ctx=None,
                tool=None,
            )
        )
        assert approval_count == 1  # Still 1, used cache

        # Third call with different command - should prompt again
        asyncio.run(
            approved_toolset.call_tool(
                "shell_exec",
                {"command": "rm /tmp/file2.txt"},
                ctx=None,
                tool=None,
            )
        )
        assert approval_count == 2  # Now 2, different command

    def test_unknown_tool_requires_approval(self):
        """Test that unknown tools require approval."""
        toolset = ShellToolset()

        # Unknown tool should return needs_approval
        result = toolset.needs_approval("unknown_tool", {"arg": "value"})
        assert result.is_needs_approval

    def test_config_overrides_defaults(self):
        """Test that config can override default safe commands."""
        toolset = ShellToolset(
            config={
                "shell_exec": {
                    "safe_commands": ["ls"],  # Only ls is safe
                },
            },
        )

        # ls should still be safe
        assert toolset.needs_approval("shell_exec", {"command": "ls -la"}).is_pre_approved

        # pwd is no longer in safe_commands, so requires approval
        result = toolset.needs_approval("shell_exec", {"command": "pwd"})
        assert result.is_needs_approval


class BlockingToolset(AbstractToolset):
    """Toolset that blocks certain operations."""

    def __init__(self) -> None:
        pass

    @property
    def id(self) -> str | None:
        return "blocking_toolset"

    async def get_tools(self, ctx: Any) -> dict:
        return {
            "do_action": {
                "description": "Do an action",
                "parameters": {"type": "object", "properties": {}},
            }
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: Any, tool: Any
    ) -> str:
        return f"Action: {name}"

    def needs_approval(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any] | None = None
    ) -> ApprovalResult:
        if tool_args.get("blocked"):
            return ApprovalResult.blocked("This operation is forbidden")
        if tool_args.get("safe"):
            return ApprovalResult.pre_approved()
        return ApprovalResult.needs_approval()


class TestBlockedOperations:
    """Tests for blocked operations."""

    def test_blocked_raises_permission_error(self):
        """Test that blocked operations raise PermissionError."""
        toolset = BlockingToolset()
        approved_toolset = ApprovalToolset(
            inner=toolset,
            approval_callback=lambda req: ApprovalDecision(approved=True),
        )

        with pytest.raises(PermissionError) as exc_info:
            asyncio.run(
                approved_toolset.call_tool(
                    "do_action",
                    {"blocked": True},
                    ctx=None,
                    tool=None,
                )
            )

        assert "forbidden" in str(exc_info.value)

    def test_blocked_never_calls_callback(self):
        """Test that blocked operations never call the approval callback."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        toolset = BlockingToolset()
        approved_toolset = ApprovalToolset(
            inner=toolset,
            approval_callback=should_not_be_called,
        )

        with pytest.raises(PermissionError):
            asyncio.run(
                approved_toolset.call_tool(
                    "do_action",
                    {"blocked": True},
                    ctx=None,
                    tool=None,
                )
            )

        assert not callback_called

    def test_pre_approved_skips_callback(self):
        """Test that pre_approved operations skip the callback."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        toolset = BlockingToolset()
        approved_toolset = ApprovalToolset(
            inner=toolset,
            approval_callback=should_not_be_called,
        )

        result = asyncio.run(
            approved_toolset.call_tool(
                "do_action",
                {"safe": True},
                ctx=None,
                tool=None,
            )
        )

        assert not callback_called
        assert "Action" in result


class TestAsyncCallbacks:
    """Tests for async approval callbacks (for web UI, Slack, etc.)."""

    def test_async_callback_approved(self):
        """Test that async callbacks work for approval."""
        approval_requests: list[ApprovalRequest] = []

        async def async_approve_callback(request: ApprovalRequest) -> ApprovalDecision:
            # Simulate async operation (e.g., sending to Slack, waiting for response)
            await asyncio.sleep(0.01)
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        def send_email(to: str, subject: str) -> str:
            """Send an email."""
            return f"Email sent to {to} with subject: {subject}"

        inner_toolset = FunctionToolset([send_email])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=async_approve_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        result = asyncio.run(
            agent.run(
                "Send email to test@example.com about Meeting",
                model=TestModel(call_tools=["send_email"]),
            )
        )

        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "send_email"

    def test_async_callback_denied(self):
        """Test that async callbacks can deny operations."""
        async def async_deny_callback(request: ApprovalRequest) -> ApprovalDecision:
            await asyncio.sleep(0.01)
            return ApprovalDecision(approved=False, note="Denied by async callback")

        def delete_file(path: str) -> str:
            """Delete a file."""
            return f"Deleted {path}"

        inner_toolset = FunctionToolset([delete_file])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=async_deny_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        with pytest.raises(PermissionError) as exc_info:
            asyncio.run(
                agent.run(
                    "Delete /tmp/test.txt",
                    model=TestModel(call_tools=["delete_file"]),
                )
            )

        assert "Denied by async callback" in str(exc_info.value)

    def test_async_callback_with_session_cache(self):
        """Test that async callbacks work with session caching."""
        callback_count = 0

        async def async_approve_with_session(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_count
            await asyncio.sleep(0.01)
            callback_count += 1
            return ApprovalDecision(approved=True, remember="session")

        def list_files(path: str) -> str:
            """List files in a directory."""
            return f"Files in {path}"

        inner_toolset = FunctionToolset([list_files])
        memory = ApprovalMemory()
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=async_approve_with_session,
            memory=memory,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        # First call - should invoke async callback
        asyncio.run(
            agent.run(
                "List files in /tmp",
                model=TestModel(call_tools=["list_files"]),
            )
        )

        # Second call with same args - should use cache
        asyncio.run(
            agent.run(
                "List files in /tmp",
                model=TestModel(call_tools=["list_files"]),
            )
        )

        # Callback should only be called once (second call uses cache)
        assert callback_count == 1

    def test_controller_request_approval(self):
        """Test ApprovalController.request_approval method."""
        async def async_callback(request: ApprovalRequest) -> ApprovalDecision:
            await asyncio.sleep(0.01)
            return ApprovalDecision(approved=True, remember="session")

        controller = ApprovalController(
            mode="interactive",
            approval_callback=async_callback,
        )

        request = ApprovalRequest(
            tool_name="test_tool",
            tool_args={"arg": "value"},
            description="Test tool call",
        )

        async def test_async():
            decision = await controller.request_approval(request)
            assert decision.approved
            assert decision.remember == "session"

            # Second call should use cache
            decision2 = await controller.request_approval(request)
            assert decision2.approved

        asyncio.run(test_async())

    def test_controller_request_approval_approve_all_mode(self):
        """Test request_approval in approve_all mode."""
        controller = ApprovalController(mode="approve_all")

        request = ApprovalRequest(
            tool_name="any_tool",
            tool_args={},
            description="Any operation",
        )

        async def test_async():
            decision = await controller.request_approval(request)
            assert decision.approved

        asyncio.run(test_async())

    def test_controller_request_approval_strict_mode(self):
        """Test request_approval in strict mode."""
        controller = ApprovalController(mode="strict")

        request = ApprovalRequest(
            tool_name="any_tool",
            tool_args={},
            description="Any operation",
        )

        async def test_async():
            decision = await controller.request_approval(request)
            assert not decision.approved
            assert "Strict mode" in decision.note

        asyncio.run(test_async())

    def test_mixed_sync_callback_with_async_toolset(self):
        """Test that sync callbacks still work with the async-capable toolset."""
        approval_requests: list[ApprovalRequest] = []

        def sync_callback(request: ApprovalRequest) -> ApprovalDecision:
            # Sync callback (no async/await)
            approval_requests.append(request)
            return ApprovalDecision(approved=True)

        def get_data(key: str) -> str:
            """Get data by key."""
            return f"Data for {key}"

        inner_toolset = FunctionToolset([get_data])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=sync_callback,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        result = asyncio.run(
            agent.run(
                "Get data for key1",
                model=TestModel(call_tools=["get_data"]),
            )
        )

        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "get_data"
