"""Tests for InventoryManager — item tracking, counting, summaries."""

from __future__ import annotations

import pytest

from minecraft_ai_bridge.bridge.inventory_manager import InventoryManager


@pytest.mark.asyncio
class TestInventoryManager:
    async def test_refresh_empty(self, mock_mc):
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.item_count == 0
        assert mgr.total_slots_used() == 0

    async def test_has_item(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "dirt", "count": 64, "slot": 0},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.has_item("dirt") is True
        assert mgr.has_item("minecraft:dirt") is True
        assert mgr.has_item("diamond") is False

    async def test_count_item(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 32, "slot": 0},
                {"item_id": "stone", "count": 16, "slot": 1},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.count_item("stone") == 48
        assert mgr.has_item("stone", 48) is True
        assert mgr.has_item("stone", 49) is False

    async def test_count_with_prefix(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 10, "slot": 0},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.count_item("minecraft:stone") == 10

    async def test_get_item_slots(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 10, "slot": 0},
                {"item_id": "stone", "count": 5, "slot": 1},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        slots = mgr.get_item_slots("stone")
        assert len(slots) == 2

    async def test_hotbar(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 10, "slot": 0},
                {"item_id": "dirt", "count": 10, "slot": 8},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        hb = mgr.get_hotbar()
        assert len(hb) == 2

    async def test_armor(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "diamond_helmet", "count": 1, "slot": 100},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        armor = mgr.get_armor()
        assert len(armor) == 1

    async def test_offhand(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "shield", "count": 1, "slot": -106},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        oh = mgr.get_offhand()
        assert len(oh) == 1

    async def test_summary(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 32, "slot": 0},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        s = mgr.summary
        assert "Inventory" in s
        assert "stone" in s.lower() or "stone" in s

    async def test_total_item_types(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 10, "slot": 0},
                {"item_id": "dirt", "count": 10, "slot": 1},
                {"item_id": "stone", "count": 5, "slot": 2},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.total_item_types() == 2

    async def test_get_all_items(self, mock_mc):
        mock_mc.set_inventory(
            [
                {"item_id": "stone", "count": 10, "slot": 0},
            ]
        )
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert len(mgr.get_all_items()) == 1

    async def test_refresh_failure(self, mock_mc):
        mock_mc.connected = False
        mgr = InventoryManager(mock_mc)
        await mgr.refresh()
        assert mgr.item_count == 0
