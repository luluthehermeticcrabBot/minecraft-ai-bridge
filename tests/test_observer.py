"""Tests for the observer and its NBT parsing functions."""

from __future__ import annotations

from minecraft_ai_bridge.minecraft.observer import (
    InventorySlot,
    _parse_inventory_nbt,
    _parse_nbt_list,
    _parse_nbt_value,
)

# No global asyncio marker — the async tests in TestObserver are individually marked


class TestObserver:
    """Integration tests using MockMcpqClient."""

    async def test_observe_position(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_position(42.0, 70.0, 100.0)
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert state.position == (42.0, 70.0, 100.0)

    async def test_observe_inventory(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_inventory(
            [
                {"item_id": "dirt", "count": 64, "slot": 0},
                {"item_id": "stone", "count": 32, "slot": 1},
            ]
        )
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert len(state.inventory) >= 2
        items_found = [s.item_id for s in state.inventory]
        assert "minecraft:dirt" in items_found or "dirt" in items_found

    async def test_observe_health(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_player_nbt("Health", 15.0)
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert state.health is not None
        assert state.health == 15.0

    async def test_observe_health_fallback(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        obs = Observer(mock_mc)
        state = await obs.observe()
        assert state.health is not None

    async def test_observe_players(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_players(["AIBot", "Player1"])
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert "AIBot" in state.players
        assert "Player1" in state.players

    async def test_observe_biome(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_position(0.0, 65.0, 0.0)
        mock_mc.set_biome("plains")
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert state.biome is not None

    async def test_observe_position_only(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_position(77.0, 64.0, -50.0)
        obs = Observer(mock_mc)
        pos = await obs.observe_position()
        assert pos == (77.0, 64.0, -50.0)

    async def test_observe_biome_error(self, mock_mc):
        from minecraft_ai_bridge.minecraft.observer import Observer

        mock_mc.set_position(0.0, 65.0, 0.0)
        mock_mc.set_biome(RuntimeError("MCPQ error"))
        obs = Observer(mock_mc)
        state = await obs.observe()
        assert state.biome == ""  # graceful degradation


class TestNbtValueParser:
    """Tests for _parse_nbt_value function."""

    def test_parse_float_double(self):
        assert _parse_nbt_value("20.0d") == 20.0

    def test_parse_int(self):
        assert _parse_nbt_value("42") == 42

    def test_parse_byte(self):
        assert _parse_nbt_value("64b") == 64

    def test_parse_negative(self):
        assert _parse_nbt_value("-10.5d") == -10.5

    def test_parse_empty(self):
        assert _parse_nbt_value("") is None

    def test_parse_whitespace(self):
        assert _parse_nbt_value("   ") is None

    def test_parse_long(self):
        assert _parse_nbt_value("100L") == 100

    def test_parse_float(self):
        assert _parse_nbt_value("5f") == 5

    def test_parse_non_numeric(self):
        result = _parse_nbt_value("no numbers here")
        assert result == "no numbers here"

    def test_parse_health_raw(self):
        assert _parse_nbt_value("Health: 20.0d") == 20.0
        assert _parse_nbt_value("Health: 0.0d") == 0.0
        assert _parse_nbt_value("15.5d") == 15.5


class TestNbtListParser:
    """Tests for _parse_nbt_list function."""

    def test_parse_position(self):
        result = _parse_nbt_list("[1.0d, 64.0d, 3.0d]")
        assert result == [1.0, 64.0, 3.0]

    def test_parse_empty(self):
        assert _parse_nbt_list("[]") is None

    def test_parse_no_match(self):
        assert _parse_nbt_list("no brackets") is None

    def test_parse_with_prefix(self):
        result = _parse_nbt_list("Position: [10.5d, -3.0d, 0d]")
        assert result == [10.5, -3.0, 0.0]

    def test_parse_int_values(self):
        result = _parse_nbt_list("[1, 2, 3]")
        assert result == [1.0, 2.0, 3.0]


class TestParseInventoryNbt:
    """Tests for _parse_inventory_nbt function."""

    def test_parse_empty(self):
        assert _parse_inventory_nbt("") == []

    def test_parse_empty_inventory(self):
        assert _parse_inventory_nbt("Inventory: []") == []

    def test_parse_single_item(self):
        raw = '[{id:"minecraft:dirt",Count:64b,Slot:0b}]'
        result = _parse_inventory_nbt(raw)
        assert len(result) == 1
        assert result[0].item_id == "minecraft:dirt"
        assert result[0].count == 64
        assert result[0].slot == 0

    def test_parse_multiple_items(self):
        raw = '[{id:"minecraft:dirt",Count:64b,Slot:0b},{id:"minecraft:stone",Count:32b,Slot:1b}]'
        result = _parse_inventory_nbt(raw)
        assert len(result) == 2
        assert result[1].item_id == "minecraft:stone"
        assert result[1].count == 32

    def test_parse_with_prefix(self):
        raw = 'Inventory: [{id:"minecraft:oak_log",Count:8b,Slot:2b}]'
        result = _parse_inventory_nbt(raw)
        assert len(result) == 1
        assert result[0].item_id == "minecraft:oak_log"

    def test_parse_with_damage(self):
        raw = '[{id:"minecraft:diamond_pickaxe",Count:1b,Slot:0b,Damage:100b}]'
        result = _parse_inventory_nbt(raw)
        assert len(result) == 1
        assert result[0].item_id == "minecraft:diamond_pickaxe"

    def test_parse_malformed(self):
        assert _parse_inventory_nbt("garbage") == []

    def test_parse_partially_valid(self):
        raw = '[{id:"minecraft:dirt",Count:64b,Slot:0b},garbage]'
        result = _parse_inventory_nbt(raw)
        assert len(result) >= 1  # should parse valid part

    def test_inventory_slot_display_name(self):
        slot = InventorySlot(item_id="minecraft:oak_planks", count=16, slot=0)
        assert slot.display_name == "oak planks"

    def test_inventory_slot_no_namespace(self):
        slot = InventorySlot(item_id="diamond", count=1, slot=5)
        assert slot.display_name == "diamond"
