"""Shared test fixtures and mock MCPQ client.

All test modules import from here to get a consistent mock environment.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from minecraft_ai_bridge.minecraft.actions import ActionType, ActionResult
from minecraft_ai_bridge.minecraft.mc_api import McpqClient
from minecraft_ai_bridge.minecraft.observer import InventorySlot, WorldState


# ── Mock MCPQ Client ──────────────────────────────────────────────────────


class MockMcpqClient:
    """A full in-memory MCPQ client mock for testing.

    Simulates a small 3D world (position, blocks, inventory, time, players).
    Tests can pre-configure the world state and then assert on actions taken.
    """

    def __init__(self) -> None:
        self.connected = True
        self._pos: tuple[float, float, float] = (0.0, 65.0, 0.0)
        self._block_map: dict[tuple[int, int, int], str] = {}
        self._inventory: list[InventorySlot] = []
        self._time: str = "day"
        self._weather: str = "clear"
        self._players: list[str] = ["AIBot"]
        self._command_log: list[str] = []  # all commands executed
        self._chat_log: list[str] = []  # chat messages sent
        self._player_nbt: dict[str, Any] = {}
        self._next_get_biome: str | Exception = "plains"

    # ── Pre-configuration helpers ─────────────────────────────────────

    def set_position(self, x: float, y: float, z: float) -> None:
        self._pos = (x, y, z)

    def set_block(self, x: int, y: int, z: int, block_type: str) -> None:
        self._block_map[(x, y, z)] = block_type

    def set_block_map(self, blocks: dict[tuple[int, int, int], str]) -> None:
        self._block_map.update(blocks)

    def set_inventory(self, items: list[dict[str, Any]]) -> None:
        self._inventory = [
            InventorySlot(
                item_id=item.get("item_id", "stone"),
                count=item.get("count", 1),
                slot=item.get("slot", 0),
                damage=item.get("damage", 0),
            )
            for item in items
        ]

    def set_time(self, time_str: str) -> None:
        self._time = time_str

    def set_players(self, players: list[str]) -> None:
        self._players = players

    def set_biome(self, biome: str | Exception) -> None:
        """Set the biome to return; pass Exception to simulate failure."""
        self._next_get_biome = biome

    def set_player_nbt(self, key: str, value: Any) -> None:
        self._player_nbt[key] = value

    # ── Assertions ────────────────────────────────────────────────────

    @property
    def commands_ran(self) -> list[str]:
        return list(self._command_log)

    @property
    def chat_messages_sent(self) -> list[str]:
        return list(self._chat_log)

    def last_command(self) -> str | None:
        return self._command_log[-1] if self._command_log else None

    def assert_command_contains(self, substring: str) -> None:
        """Assert at least one command contains the given substring."""
        for cmd in self._command_log:
            if substring in cmd:
                return
        pytest.fail(f"No command contained {substring!r}. Commands: {self._command_log}")

    def assert_chat_contains(self, substring: str) -> None:
        """Assert at least one chat message contains the given substring."""
        for msg in self._chat_log:
            if substring in msg:
                return
        pytest.fail(f"No chat message contained {substring!r}. Messages: {self._chat_log}")

    async def connect(self, **kwargs: Any) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_player(self) -> Any:
        class MockPlayer:
            name = "AIBot"
            pos = type("Pos", (), {"x": 0.0, "y": 65.0, "z": 0.0})()
            world = type("World", (), {"name": "world"})()
            async def getNbt(self):  # noqa: N802
                return self._nbt or {}
            _nbt = {}
        p = MockPlayer()
        p._nbt = self._player_nbt
        return p

    async def get_player_pos(self) -> tuple[float, float, float] | None:
        return self._pos

    async def get_player_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "online": True,
            "name": "AIBot",
            "pos": {"x": self._pos[0], "y": self._pos[1], "z": self._pos[2]},
            "world": "world",
        }
        if "Health" in self._player_nbt:
            info["health"] = self._player_nbt["Health"]
        return info

    async def teleport_player(self, x: float, y: float, z: float) -> None:
        self._pos = (x, y, z)
        self._command_log.append(f"teleport to ({x}, {y}, {z})")

    async def get_block(self, x: int, y: int, z: int) -> str:
        return self._block_map.get((x, y, z), "air")

    async def set_block(self, block_type: str, x: int, y: int, z: int) -> None:
        self._block_map[(int(x), int(y), int(z))] = block_type
        self._command_log.append(f"set_block {block_type} at ({x}, {y}, {z})")

    async def run_command(self, command: str) -> None:
        self._command_log.append(command)

    async def run_command_blocking(self, command: str) -> str:
        self._command_log.append(command)
        # Simulate common command responses
        cmd = command.lower().strip()
        if cmd.startswith("data get entity @p health"):
            if "Health" in self._player_nbt:
                return f"Health: {self._player_nbt['Health']}d"
            return "Health: 20.0d"
        if cmd.startswith("data get entity @p inventory"):
            if not self._inventory:
                return "Inventory: []"
            parts = []
            for s in self._inventory:
                parts.append(f'{{id:"minecraft:{s.item_id}",Count:{s.count}b,Slot:{s.slot}b}}')
            return f"Inventory: [{','.join(parts)}]"
        if cmd.startswith("data get entity @p"):
            return "{}"
        if cmd.startswith("tp "):
            # Record teleport command
            return "Teleported"
        if cmd.startswith("time query day"):
            return f"{self._time}"
        if cmd.startswith("weather query"):
            return self._weather
        if cmd.startswith("execute positioned"):
            return "Located biome plains at [0, 65, 0]"
        if cmd.startswith("give @p"):
            return f"Gave 1 {cmd.split()[2]} to AIBot"
        if cmd.startswith("clear @p"):
            return "Cleared items"
        if cmd.startswith("summon item"):
            return "Spawned item entity"
        if cmd.startswith("damage"):
            return "Damaged 1 entity"
        if cmd.startswith("botsummon"):
            return "Summoned bot"
        if cmd.startswith("setblock"):
            if "Changed the block" in cmd or "block changed" in cmd:
                return "Changed the block"
            return "Changed the block"
        if cmd.startswith("item replace"):
            return "Replaced item"
        if cmd.startswith("attribute @p"):
            return "20.0"
        if cmd.startswith("execute as @p at @s run tp"):
            return "Teleported"
        if cmd.startswith("execute as @p at @s run interact"):
            return "Interacted"
        if cmd.startswith("execute if biome"):
            return "false"  # biome fallback test returns false by default
        return "OK"

    async def post_to_chat(self, message: str) -> None:
        self._chat_log.append(message)
        self._command_log.append(f"chat: {message}")

    async def get_biome(self, x: int, y: int, z: int) -> str:
        if isinstance(self._next_get_biome, Exception):
            raise self._next_get_biome
        return self._next_get_biome

    async def set_sign(self, **kwargs: Any) -> None:
        pass

    async def get_time(self) -> str:
        return self._time

    async def get_players_online(self) -> list[str]:
        return self._players

    async def get_server_version(self) -> str:
        return "Paper 26.1.2"


# ── Mock Observer ────────────────────────────────────────────────────────


def make_mock_world_state(**overrides: Any) -> WorldState:
    """Create a WorldState with sensible defaults for testing."""
    state = WorldState(
        position=overrides.get("position", (0.0, 65.0, 0.0)),
        health=overrides.get("health", 20.0),
        inventory_raw=overrides.get("inventory_raw", "Inventory: []"),
        inventory=overrides.get("inventory", []),
        time_raw=overrides.get("time_raw", "day"),
        weather_raw=overrides.get("weather_raw", "clear"),
        players=overrides.get("players", ["AIBot"]),
        biome=overrides.get("biome", "plains"),
        scan_data=overrides.get("scan_data", {}),
        last_action_result=overrides.get("last_action_result", ""),
    )
    return state


# ── Pytest fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mock_mc() -> AsyncGenerator[MockMcpqClient, None]:
    """Provide a fresh MockMcpqClient with default state."""
    client = MockMcpqClient()
    yield client


@pytest.fixture
def world_state() -> WorldState:
    """Provide a default WorldState."""
    return make_mock_world_state()


# ── Async mock helper ────────────────────────────────────────────────────


class AsyncMock:
    """A simple async-compatible mock.

    Usage::

        mock = AsyncMock(return_value=42)
        result = await mock()  # → 42
    """

    def __init__(self, return_value: Any = None, side_effect: Any = None) -> None:
        self._return_value = return_value
        self._side_effect = side_effect
        self.call_count = 0
        self.calls: list[tuple[Any, ...]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        self.calls.append((args, kwargs))
        if self._side_effect is not None:
            if isinstance(self._side_effect, Exception):
                raise self._side_effect
            if callable(self._side_effect):
                return await self._side_effect(*args, **kwargs)
        return self._return_value

    def assert_called_once(self) -> None:
        assert self.call_count == 1, f"Expected 1 call, got {self.call_count}"

    def assert_not_called(self) -> None:
        assert self.call_count == 0, f"Expected 0 calls, got {self.call_count}"


class MockLLMClient:
    """A mock LLM client that returns pre-configured responses.

    Tests set ``responses`` as a queue of (action, params) tuples.
    """

    def __init__(self, responses: list[tuple[str, dict[str, Any]]] | None = None) -> None:
        self._responses = responses or [("done", {"message": "test"})]
        self._index = 0
        self._decompose_return: list[dict[str, Any]] | None = None
        self.prompts_received: list[str] = []

    async def decide(
        self,
        system_prompt: str,
        messages: list,
        tool_choice: str = "auto",
    ) -> Any:
        self.prompts_received.append(system_prompt[:100])
        from minecraft_ai_bridge.llm.models import LLMResponse
        if self._index >= len(self._responses):
            return LLMResponse(action="done", action_params={}, reasoning="No more responses")
        action, params = self._responses[self._index]
        self._index += 1
        return LLMResponse(action=action, action_params=params, reasoning="test reasoning")

    async def decompose_goal(self, goal: str) -> list[dict[str, Any]]:
        if self._decompose_return is not None:
            return self._decompose_return
        return []  # empty → triggers fallback

    def set_decompose_return(self, subgoals: list[dict[str, Any]]) -> None:
        self._decompose_return = subgoals
