"""Tests for in-game chat command parsing and dispatch."""

from __future__ import annotations

import pytest

from minecraft_ai_bridge.bridge.chat_commands import (
    ChatCommandHandler,
    _COMMAND_RE,
    COMMANDS,
)
from minecraft_ai_bridge.bridge.memory import AgentMemory


class TestCommandParsing:
    """Regex-based chat command parser."""

    def test_match_basic(self):
        m = _COMMAND_RE.match("<Player> !status")
        assert m is not None
        assert m.group(1) == "Player"
        assert m.group(2).strip() == "!status"

    def test_match_with_args(self):
        m = _COMMAND_RE.match("<Player> !goal Build a house")
        assert m is not None
        assert m.group(2).strip() == "!goal"
        assert "Build a house" in m.group(3)

    def test_regular_chat(self):
        m = _COMMAND_RE.match("<Player> Hello everyone!")
        assert m is None

    def test_empty(self):
        m = _COMMAND_RE.match("")
        assert m is None

    def test_with_slash_prefix(self):
        m = _COMMAND_RE.match("<Player> /!stop")
        assert m is not None
        assert m.group(2).strip() in ("/!stop", "!stop")

    def test_unicode_player(self):
        m = _COMMAND_RE.match("<Jos> !status")
        assert m is not None

    def test_commands_set(self):
        assert "!status" in COMMANDS
        assert "!stop" in COMMANDS
        assert "!goal" in COMMANDS
        assert "!goto" in COMMANDS
        assert "!follow" in COMMANDS
        assert "!come" in COMMANDS
        assert "!help" in COMMANDS
        assert "!nonexistent" not in COMMANDS


class TestHarness:
    """Minimal orchestrator substitute."""

    def __init__(self):
        from tests.conftest import MockMcpqClient
        self._mc = MockMcpqClient()
        self._stop_requested = False
        self._follow_target = None
        self._memory = AgentMemory(window=5)
        self._goals = None
        self._turn = 0


@pytest.fixture
def harness():
    return TestHarness()


@pytest.mark.asyncio
class TestCommandDispatch:
    async def test_handle_stop(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!stop", "", "Player")
        assert harness._stop_requested
        assert any("Shutting down" in m for m in harness._mc.chat_messages_sent)

    async def test_handle_help(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!help", "", "Player")
        assert any("!status" in m for m in harness._mc.chat_messages_sent)

    async def test_handle_goto_no_args(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!goto", "", "Player")
        assert any("Usage" in m for m in harness._mc.chat_messages_sent)

    async def test_handle_goto(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!goto", "Player2", "Player")
        harness._mc.assert_command_contains("tp @p Player2")

    async def test_handle_follow(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!follow", "Player2", "Player")
        assert harness._follow_target == "Player2"

    async def test_handle_follow_no_args(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!follow", "", "Player")
        assert any("Usage" in m for m in harness._mc.chat_messages_sent)

    async def test_handle_goal_no_args(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!goal", "", "Player")
        assert any("Usage" in m for m in harness._mc.chat_messages_sent)

    async def test_unknown_command(self, harness):
        handler = ChatCommandHandler(harness)
        await handler.handle_command("!fake", "", "Player")
        # No crash expected

    async def test_process_valid_line(self, harness):
        handler = ChatCommandHandler(harness)
        await handler._process_line("<Player> !status")
        # Should not crash

    async def test_process_non_command(self, harness):
        handler = ChatCommandHandler(harness)
        await handler._process_line("<Player> just chatting")
        # Should be a no-op
