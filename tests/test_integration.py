"""Integration tests with PydanticAI Agent and TestModel."""
import asyncio
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.toolsets.abstract import AbstractToolset

from pydantic_ai_blocking_approval import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalBlocked,
    ApprovalRequest,
    ApprovalResult,
    ApprovalToolset,
)


# Mock context for testing needs_approval directly
MOCK_CTX: Any = None  # Tests that call needs_approval directly can pass None


class TestApprovalIntegration:
    """Integration tests for approval flow with real agent."""

    def test_tool_requires_approval_and_denied(self):
        """Test that a tool requires approval by default and raises ApprovalDenied when denied."""
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
        # When approval is denied, ApprovalDenied should be raised
        with pytest.raises(ApprovalDenied) as exc_info:
            asyncio.run(
                agent.run(
                    "Delete the file /tmp/test.txt",
                    model=TestModel(call_tools=["delete_file"]),
                )
            )

        # The approval callback should have been called
        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "delete_file"

        # The exception message should indicate denial
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

    def test_tool_bool_callback_raises(self):
        """Test that a bool callback raises TypeError."""

        def approve_all(request: ApprovalRequest) -> bool:
            return True

        def send_email(to: str, subject: str) -> str:
            """Send an email."""
            return f"Email sent to {to} with subject: {subject}"

        inner_toolset = FunctionToolset([send_email])
        approved_toolset = ApprovalToolset(
            inner=inner_toolset,
            approval_callback=approve_all,
        )

        agent = Agent(
            model=TestModel(),
            toolsets=[approved_toolset],
        )

        with pytest.raises(TypeError, match="ApprovalDecision"):
            asyncio.run(
                agent.run(
                    "Send email to test@example.com about Meeting",
                    model=TestModel(call_tools=["send_email"]),
                )
            )

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


class AsyncNeedsApprovalToolset(AbstractToolset):
    """Toolset with async needs_approval for testing."""

    @property
    def id(self) -> str | None:
        return "async_needs_approval_toolset"

    async def get_tools(self, ctx: Any) -> dict:
        return {
            "ping": {
                "description": "Ping tool",
                "parameters": {"type": "object", "properties": {}},
            }
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: Any, tool: Any
    ) -> str:
        if name != "ping":
            raise ValueError(f"Unknown tool: {name}")
        return "pong"

    async def needs_approval(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any] | None = None,
        config: dict[str, dict[str, Any]] | None = None,
    ) -> ApprovalResult:
        await asyncio.sleep(0)
        if name == "ping":
            return ApprovalResult.pre_approved()
        return ApprovalResult.needs_approval()


class TestAsyncNeedsApproval:
    """Tests for async needs_approval support."""

    def test_async_needs_approval_pre_approved(self):
        """Async needs_approval should be awaited and skip the callback."""
        callback_called = False

        def should_not_be_called(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal callback_called
            callback_called = True
            return ApprovalDecision(approved=True)

        toolset = AsyncNeedsApprovalToolset()
        approved_toolset = ApprovalToolset(
            inner=toolset,
            approval_callback=should_not_be_called,
        )

        result = asyncio.run(
            approved_toolset.call_tool(
                "ping",
                {},
                ctx=None,
                tool=None,
            )
        )

        assert result == "pong"
        assert not callback_called


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

    def __init__(self) -> None:
        self._executed_commands: list[str] = []
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
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any] | None = None,
        config: dict[str, dict[str, Any]] | None = None,
    ) -> ApprovalResult:
        """Decide if shell command needs approval based on patterns.

        Implements SupportsNeedsApproval protocol.
        ctx can be None for testing purposes.
        """
        self._last_description = None
        # ctx is available for user-specific logic (e.g., ctx.deps)
        config = config or {}
        tool_config = config.get(name, {})

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
                if not self._is_safe_read_path(path, safe_paths):
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

    @staticmethod
    def _is_safe_read_path(path: str, safe_paths: Iterable[str]) -> bool:
        candidate = PurePosixPath(path)
        if not candidate.parts:
            return False

        if candidate.is_absolute():
            for safe in safe_paths:
                if safe == ".":
                    continue
                safe_path = PurePosixPath(safe)
                if not safe_path.is_absolute():
                    continue
                if candidate.parts[: len(safe_path.parts)] == safe_path.parts:
                    return True
            return False

        if ".." in candidate.parts:
            return False

        for safe in safe_paths:
            if safe == ".":
                return True
            safe_path = PurePosixPath(safe)
            if safe_path.is_absolute():
                continue
            if candidate.parts[: len(safe_path.parts)] == safe_path.parts:
                return True
        return False


class TestShellToolsetWithApproval:
    """Tests for ShellToolset with SupportsNeedsApproval and ApprovalToolset wrapper."""

    def test_needs_approval_safe_commands(self):
        """Test that safe commands return pre_approved from needs_approval."""
        toolset = ShellToolset()
        config = {}

        # Safe commands should return pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "ls -la"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "pwd"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "whoami"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "date"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "echo hello"}, config=config
        ).is_pre_approved

    def test_needs_approval_dangerous_patterns(self):
        """Test that dangerous patterns return needs_approval with custom description."""
        toolset = ShellToolset()
        config = {}

        # rm command
        result = toolset.needs_approval(
            "shell_exec", {"command": "rm -rf /tmp/files"}, config=config
        )
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "rm -rf /tmp/files"})
        assert "dangerous" in desc.lower()
        assert "rm -rf /tmp/files" in desc

        # sudo command
        result = toolset.needs_approval(
            "shell_exec", {"command": "sudo apt update"}, config=config
        )
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "sudo apt update"})
        assert "dangerous" in desc.lower()

        # pipe
        result = toolset.needs_approval(
            "shell_exec", {"command": "ls | grep foo"}, config=config
        )
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "ls | grep foo"})
        assert "dangerous" in desc.lower()

        # redirect
        result = toolset.needs_approval(
            "shell_exec", {"command": "echo x > file"}, config=config
        )
        assert result.is_needs_approval

        # command substitution
        result = toolset.needs_approval(
            "shell_exec", {"command": "echo $(whoami)"}, config=config
        )
        assert result.is_needs_approval

    def test_needs_approval_cat_safe_paths(self):
        """Test that cat on safe paths doesn't require approval."""
        toolset = ShellToolset()
        config = {}

        # Safe paths
        assert toolset.needs_approval(
            "shell_exec", {"command": "cat /tmp/test.log"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "cat /var/log/syslog"}, config=config
        ).is_pre_approved
        assert toolset.needs_approval(
            "shell_exec", {"command": "cat ./local.txt"}, config=config
        ).is_pre_approved

    def test_needs_approval_cat_unsafe_paths(self):
        """Test that cat on sensitive paths requires approval."""
        toolset = ShellToolset()
        config = {}

        # Unsafe paths
        result = toolset.needs_approval(
            "shell_exec", {"command": "cat /etc/passwd"}, config=config
        )
        assert result.is_needs_approval
        desc = toolset.get_approval_description("shell_exec", {"command": "cat /etc/passwd"})
        assert "/etc/passwd" in desc

        result = toolset.needs_approval(
            "shell_exec", {"command": "cat /home/user/.ssh/id_rsa"}, config=config
        )
        assert result.is_needs_approval

        result = toolset.needs_approval(
            "shell_exec", {"command": "cat ../etc/passwd"}, config=config
        )
        assert result.is_needs_approval

    def test_needs_approval_unknown_commands(self):
        """Test that unknown commands require approval with description."""
        toolset = ShellToolset()
        config = {}

        result = toolset.needs_approval(
            "shell_exec", {"command": "mycustomtool --flag"}, config=config
        )
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
        """Test ApprovalToolset raises ApprovalDenied when denied."""
        shell_toolset = ShellToolset()
        approved_toolset = ApprovalToolset(
            inner=shell_toolset,
            approval_callback=lambda req: ApprovalDecision(
                approved=False, note="Too dangerous"
            ),
        )

        with pytest.raises(ApprovalDenied) as exc_info:
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

    def test_unknown_tool_requires_approval(self):
        """Test that unknown tools require approval."""
        toolset = ShellToolset()
        config = {}

        # Unknown tool should return needs_approval
        result = toolset.needs_approval(
            "unknown_tool", {"arg": "value"}, config=config
        )
        assert result.is_needs_approval

    def test_config_overrides_defaults(self):
        """Test that config can override default safe commands."""
        toolset = ShellToolset()
        config = {
            "shell_exec": {
                "safe_commands": ["ls"],  # Only ls is safe
            },
        }

        # ls should still be safe
        assert toolset.needs_approval(
            "shell_exec", {"command": "ls -la"}, config=config
        ).is_pre_approved

        # pwd is no longer in safe_commands, so requires approval
        result = toolset.needs_approval(
            "shell_exec", {"command": "pwd"}, config=config
        )
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
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any] | None = None,
        config: dict[str, dict[str, Any]] | None = None,
    ) -> ApprovalResult:
        if tool_args.get("blocked"):
            return ApprovalResult.blocked("This operation is forbidden")
        if tool_args.get("safe"):
            return ApprovalResult.pre_approved()
        return ApprovalResult.needs_approval()


class TestBlockedOperations:
    """Tests for blocked operations."""

    def test_blocked_raises_permission_error(self):
        """Test that blocked operations raise ApprovalBlocked."""
        toolset = BlockingToolset()
        approved_toolset = ApprovalToolset(
            inner=toolset,
            approval_callback=lambda req: ApprovalDecision(approved=True),
        )

        with pytest.raises(ApprovalBlocked) as exc_info:
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

        with pytest.raises(ApprovalBlocked):
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

        with pytest.raises(ApprovalDenied) as exc_info:
            asyncio.run(
                agent.run(
                    "Delete /tmp/test.txt",
                    model=TestModel(call_tools=["delete_file"]),
                )
            )

        assert "Denied by async callback" in str(exc_info.value)

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
