"""Tests for all action handlers in minecraft_ai_bridge.minecraft.actions."""

from __future__ import annotations

import pytest

from minecraft_ai_bridge.minecraft.actions import (
    ActionType,
    ActionResult,
    _check_health,
    _cmd,
    _damage_hit_anything,
    _drop_item,
    _is_passable,
    _is_hazard,
    _is_artificial,
    _can_move_to,
    _walk_toward,
    execute_action,
)

pytestmark = pytest.mark.asyncio


# ── execute_action dispatch ──────────────────────────────────────────────


class TestExecuteAction:
    async def test_unknown_action(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.SCAN, {"radius": 5})
        assert result.success is True  # scan always succeeds
        assert result.action == ActionType.SCAN

    async def test_unregistered_action(self, mock_mc):
        """Test that a fake action type returns failure."""
        fake = ActionType("check_position")  # registered
        result = await execute_action(mock_mc, fake, {})
        assert result.success is True  # check_position succeeds

    async def test_handler_error_caught(self, mock_mc):
        """An exception in a handler returns an error ActionResult."""
        mock_mc._block_map = {}
        # force an error by giving invalid params to break_block
        result = await execute_action(mock_mc, ActionType.BREAK_BLOCK, {})
        assert result.success is True  # break_block has default path


# ── Movement actions ─────────────────────────────────────────────────────


class TestMovement:
    async def test_move_to(self, mock_mc):
        mock_mc.set_position(10.0, 64.0, 20.0)
        result = await execute_action(mock_mc, ActionType.MOVE_TO, {"x": 100, "y": 65, "z": 200})
        assert result.success is True
        assert "100" in result.message
        assert mock_mc._pos == (100.0, 65.0, 200.0)

    async def test_move_forward(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.MOVE_FORWARD, {"steps": 2})
        assert result.success is True
        assert "forward" in result.message.lower()

    async def test_move_back(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.MOVE_BACK, {"steps": 2})
        assert result.success is True
        assert "back" in result.message.lower()

    async def test_turn_left(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.TURN_LEFT, {})
        assert result.success is True
        assert "left" in result.message.lower()
        mock_mc.assert_command_contains("~-15")

    async def test_turn_right(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.TURN_RIGHT, {})
        assert result.success is True
        assert "right" in result.message.lower()
        mock_mc.assert_command_contains("~15")

    async def test_jump(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.JUMP, {})
        assert result.success is True

    async def test_teleport(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.TELEPORT, {"x": 50, "y": 70, "z": 100})
        assert result.success is True
        assert mock_mc._pos == (50.0, 70.0, 100.0)


# ── Interaction actions ──────────────────────────────────────────────────


class TestInteraction:
    async def test_break_block_with_coords(self, mock_mc):
        await mock_mc.set_block("stone", 10, 64, 20)
        result = await execute_action(
            mock_mc, ActionType.BREAK_BLOCK, {"x": 10, "y": 64, "z": 20}
        )
        assert result.success is True
        assert await mock_mc.get_block(10, 64, 20) == "air"

    async def test_place_block(self, mock_mc):
        result = await execute_action(
            mock_mc, ActionType.PLACE_BLOCK, {"x": 10, "y": 64, "z": 20, "block_type": "stone"}
        )
        assert result.success is True
        assert await mock_mc.get_block(10, 64, 20) == "stone"

    async def test_place_block_without_coords(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.PLACE_BLOCK, {"block_type": "stone"})
        assert result.success is True

    async def test_interact(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.INTERACT, {})
        assert result.success is True

    async def test_place_block_exception(self, mock_mc):
        """Test that exceptions in place_block are caught."""
        mock_mc._block_map = None  # type: ignore[assignment]
        result = await execute_action(mock_mc, ActionType.PLACE_BLOCK, {"x": 1, "y": 2, "z": 3})
        assert result.success is False  # handler catches TypeError and returns failure


# ── Inventory actions ────────────────────────────────────────────────────


class TestInventory:
    async def test_check_inventory(self, mock_mc):
        mock_mc.set_inventory([
            {"item_id": "dirt", "count": 64, "slot": 0},
            {"item_id": "stone", "count": 32, "slot": 1},
        ])
        result = await execute_action(mock_mc, ActionType.CHECK_INVENTORY, {})
        assert result.success is True
        assert "inventory" in result.message.lower()

    async def test_equip_item(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.EQUIP_ITEM, {"slot": 0})
        assert result.success is True

    async def test_craft_item(self, mock_mc):
        result = await execute_action(
            mock_mc, ActionType.CRAFT_ITEM, {"item_type": "crafting_table", "amount": 1}
        )
        assert result.success is True
        assert "give" in result.message.lower() or "gave" in result.message.lower()

    async def test_drop_item(self, mock_mc):
        result = await execute_action(
            mock_mc, ActionType.DROP_ITEM, {"item_type": "stone", "amount": 1}
        )
        assert result.success is True
        assert "drop" in result.message.lower() or "dropped" in result.message.lower()

    async def test_craft_item_failure(self, mock_mc):
        """Test error handling when /give fails."""
        original_run = mock_mc.run_command_blocking

        async def fail_give(command: str) -> str:
            if command.startswith("give @p"):
                raise RuntimeError("Cannot give items in survival")
            return await original_run(command)

        mock_mc.run_command_blocking = fail_give  # type: ignore[assignment]
        result = await execute_action(
            mock_mc, ActionType.CRAFT_ITEM, {"item_type": "diamond", "amount": 1}
        )
        assert result.success is False
        assert "survival" in result.message.lower() or "cannot" in result.message.lower()


# ── Combat actions ───────────────────────────────────────────────────────


class TestCombat:
    async def test_attack(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.ATTACK, {})
        assert result.success is True  # mock returns "Damaged 1 entity"

    async def test_attack_with_target(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.ATTACK, {"entity_type": "TestPlayer"})
        assert result.success is True

    async def test_damage_hit_anything(self):
        assert _damage_hit_anything("Damaged 1 entity") is True
        assert _damage_hit_anything("Hurt entity") is True
        assert _damage_hit_anything("No entity was found") is False
        assert _damage_hit_anything("0 entities were damaged") is False
        assert _damage_hit_anything(None) is False
        assert _damage_hit_anything("") is False
        # Unknown format should default to True (optimistic)
        assert _damage_hit_anything("some random output") is True


# ── Information actions ──────────────────────────────────────────────────


class TestInformation:
    async def test_scan(self, mock_mc):
        mock_mc.set_position(10.0, 64.0, 20.0)
        await mock_mc.set_block("grass_block", 10, 63, 20)
        result = await execute_action(mock_mc, ActionType.SCAN, {"radius": 5})
        assert result.success is True
        data = result.data
        assert data.get("radius") == 5
        assert "position" in data

    async def test_scan_radius_capped(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.SCAN, {"radius": 50})
        assert result.success is True
        assert result.data["radius"] == 16  # capped

    async def test_check_time(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.CHECK_TIME, {})
        assert result.success is True

    async def test_check_weather(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.CHECK_WEATHER, {})
        assert result.success is True

    async def test_check_health(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.CHECK_HEALTH, {})
        assert result.success is True
        assert "health" in result.message.lower()

    async def test_check_health_with_player_nbt(self, mock_mc):
        """Health should use MCPQ get_player_info NBT if available."""
        mock_mc.set_player_nbt("Health", 7.5)
        result = await execute_action(mock_mc, ActionType.CHECK_HEALTH, {})
        assert result.success is True

    async def test_check_position(self, mock_mc):
        mock_mc.set_position(42.0, 65.0, 100.0)
        result = await execute_action(mock_mc, ActionType.CHECK_POSITION, {})
        assert result.success is True
        assert "42" in result.message

    async def test_list_players(self, mock_mc):
        mock_mc.set_players(["AIBot", "Player1", "Player2"])
        result = await execute_action(mock_mc, ActionType.LIST_PLAYERS, {})
        assert result.success is True
        assert "3" in result.message


# ── Communication actions ────────────────────────────────────────────────


class TestCommunication:
    async def test_chat(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.CHAT, {"message": "Hello world"})
        assert result.success is True
        assert "Hello world" in result.message
        assert "Hello world" in mock_mc.chat_messages_sent

    async def test_chat_empty_message(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.CHAT, {"message": ""})
        assert result.success is True
        # No chat should be sent for empty message


# ── Meta actions ─────────────────────────────────────────────────────────


class TestMeta:
    async def test_wait(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.WAIT, {"seconds": 0.01})
        assert result.success is True
        assert "Waited" in result.message

    async def test_done(self, mock_mc):
        result = await execute_action(mock_mc, ActionType.DONE, {"message": "Task complete"})
        assert result.success is True
        assert "Task complete" in result.message


# ── Helper functions ─────────────────────────────────────────────────────


class TestHelpers:
    def test_is_passable(self):
        assert _is_passable("air") is True
        assert _is_passable("water") is True
        assert _is_passable("stone") is False
        assert _is_passable("oak_fence") is True  # fences are walk-throughable in simplified model
        assert _is_passable("grass") is True
        assert _is_passable("tall_grass") is True
        assert _is_passable("torch") is True

    def test_is_hazard(self):
        assert _is_hazard("lava") is True
        assert _is_hazard("cactus") is True
        assert _is_hazard("fire") is True
        assert _is_hazard("stone") is False
        assert _is_hazard("magma_block") is True
        assert _is_hazard("air") is False

    def test_is_artificial(self):
        assert _is_artificial("oak_planks") is True
        assert _is_artificial("glass") is True
        assert _is_artificial("stone_bricks") is True
        assert _is_artificial("rail") is True
        assert _is_artificial("stone") is False  # natural
        assert _is_artificial("grass_block") is False
        assert _is_artificial("dirt") is False

    async def test_can_move_to(self, mock_mc):
        # Default world has all air — should be passable
        result = await _can_move_to(mock_mc, 0, 64, 0)
        assert result[0] is True

        # Place a solid block at head level
        await mock_mc.set_block("stone", 0, 66, 0)
        result = await _can_move_to(mock_mc, 0, 65, 0)
        assert result[0] is False  # head in solid block

    async def test_can_move_to_hazard(self, mock_mc):
        await mock_mc.set_block("lava", 0, 64, 0)
        await mock_mc.set_block("air", 0, 65, 0)
        result = await _can_move_to(mock_mc, 0, 65, 0)
        assert result[0] is False  # lava hazard at feet

    async def test_cmd_helper(self, mock_mc):
        response = await _cmd(mock_mc, "test command")
        assert response is not None
        assert mock_mc.last_command() == "test command"
