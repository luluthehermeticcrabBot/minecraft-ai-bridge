"""Tests for prompt formatting utilities."""

from __future__ import annotations

from minecraft_ai_bridge.llm.models import AgentGoal
from minecraft_ai_bridge.llm.prompts import format_goal, format_state, summarize_result


class TestFormatGoal:
    def test_no_subgoals(self):
        goal = AgentGoal(description="Build a house")
        r = format_goal(goal)
        assert "Build a house" in r
        assert "Sub-goals" not in r

    def test_with_subgoals(self):
        goal = AgentGoal(
            description="Build a house",
            sub_goals=[
                AgentGoal(description="Gather wood", depth=1),
                AgentGoal(description="Craft planks", depth=1),
            ],
        )
        r = format_goal(goal)
        assert "Gather wood" in r
        assert "Craft planks" in r
        assert "○" in r

    def test_with_completed(self):
        goal = AgentGoal(
            description="Build a house",
            sub_goals=[
                AgentGoal(description="Gather wood", completed=True, depth=1),
            ],
        )
        r = format_goal(goal)
        assert "✓" in r


class TestFormatState:
    def test_position(self):
        r = format_state({"position": (10.5, 65.0, -20.3)})
        assert "10.5" in r
        assert "-20.3" in r

    def test_health(self):
        r = format_state({"health": 15.0})
        assert "15" in r
        assert "20" in r

    def test_no_health(self):
        r = format_state({})
        assert "Health" not in r

    def test_inventory_with_dataclass(self):
        slot = type("Slot", (), {"display_name": "dirt", "count": 64})()
        r = format_state({"inventory": [slot]})
        assert "dirt" in r

    def test_inventory_with_dict(self):
        r = format_state({"inventory": [{"display_name": "oak log", "count": 8}]})
        assert "oak log" in r

    def test_inventory_empty(self):
        r = format_state({"inventory": []})
        assert "empty" in r

    def test_inventory_raw_fallback(self):
        r = format_state({"inventory": [], "inventory_raw": "some raw data"})
        assert "raw" in r.lower() or "inventory" in r.lower()

    def test_biome(self):
        r = format_state({"biome": "desert"})
        assert "desert" in r

    def test_time(self):
        r = format_state({"time_raw": "day"})
        assert "day" in r or "Time" in r

    def test_scan_nearby(self):
        r = format_state(
            {
                "scan_data": {"nearby": {"north": "stone", "south": "air"}},
            }
        )
        assert "north" in r
        assert "stone" in r


class TestSummarizeResult:
    def test_success(self):
        r = summarize_result("move_forward", {"success": True, "message": "ok"})
        assert "✓" in r
        assert "move_forward" in r

    def test_failure(self):
        r = summarize_result("break_block", {"success": False, "message": "fail"})
        assert "✗" in r

    def test_empty_message(self):
        r = summarize_result("wait", {"success": True, "message": ""})
        assert "wait" in r
