"""Tests for GoalManager — decomposition, fallback plans, progress tracking."""

from __future__ import annotations

import pytest

from minecraft_ai_bridge.bridge.goal_manager import GoalManager
from minecraft_ai_bridge.llm.models import AgentGoal


@pytest.fixture
def mock_llm():
    from tests.conftest import MockLLMClient

    return MockLLMClient()


@pytest.fixture
def gm(mock_llm):
    return GoalManager(llm_client=mock_llm, max_depth=5)


@pytest.mark.asyncio
class TestGoalDecomposition:
    async def test_set_goal_without_llm(self):
        gm2 = GoalManager(llm_client=None)
        root = await gm2.set_goal("Build a house")
        assert root is not None
        assert len(root.sub_goals) > 0

    async def test_set_goal_with_llm(self, gm, mock_llm):
        mock_llm.set_decompose_return(
            [
                {"step": 1, "description": "Gather wood", "expected_actions": ["check"]},
                {"step": 2, "description": "Craft planks", "expected_actions": ["craft"]},
            ]
        )
        root = await gm.set_goal("Build a house")
        assert len(root.sub_goals) == 2
        assert root.sub_goals[0].description == "Gather wood"

    async def test_empty_llm_triggers_fallback(self, gm):
        root = await gm.set_goal("Mine for diamonds")
        assert len(root.sub_goals) > 0

    async def test_set_from_subgoals(self, gm):
        root = gm.set_goal_from_subgoals(
            "Test",
            [
                {"description": "Step 1"},
                {"description": "Step 2"},
            ],
        )
        assert len(root.sub_goals) == 2


@pytest.mark.asyncio
class TestFallbackPlans:
    async def test_build_plan(self, gm):
        root = await gm.set_goal("Build a cobblestone house")
        assert len(root.sub_goals) == 11

    async def test_mine_plan(self, gm):
        root = await gm.set_goal("Mine for diamonds")
        assert len(root.sub_goals) == 12

    async def test_farm_plan(self, gm):
        root = await gm.set_goal("Farm wheat for bread")
        descs = [s.description for s in root.sub_goals]
        assert len(descs) == 10
        assert any("seed" in d.lower() for d in descs)

    async def test_workshop_plan(self, gm):
        root = await gm.set_goal("Craft an enchanting table")
        assert len(root.sub_goals) == 9

    async def test_explore_plan(self, gm):
        root = await gm.set_goal("Explore the area")
        assert len(root.sub_goals) == 8

    async def test_teleport_plan(self, gm):
        root = await gm.set_goal("Teleport to 100 64 -200")
        assert len(root.sub_goals) == 4

    async def test_combat_plan(self, gm):
        root = await gm.set_goal("Kill the zombie")
        assert len(root.sub_goals) == 7

    async def test_describe_plan(self, gm):
        root = await gm.set_goal("Describe your surroundings")
        assert len(root.sub_goals) == 5

    async def test_generic_plan(self, gm):
        root = await gm.set_goal("Do something completely unique")
        assert len(root.sub_goals) == 6
        for sg in root.sub_goals:
            assert "Do something completely unique" in sg.description

    async def test_case_insensitive(self, gm):
        root = await gm.set_goal("BUILD A BRIDGE")
        assert len(root.sub_goals) == 11

    async def test_first_match_wins(self, gm):
        root = await gm.set_goal("Build a mine")
        assert len(root.sub_goals) == 11  # build plan (first match)


@pytest.mark.asyncio
class TestProgressTracking:
    async def test_initial_goal(self, gm):
        await gm.set_goal("Explore")
        assert gm.current_goal is not None
        assert gm.current_goal != "All goals complete!"

    async def test_advance(self, gm):
        await gm.set_goal("Explore")
        first = gm.current_goal
        gm.mark_current_complete()
        second = gm.current_goal
        assert second != first

    async def test_not_complete_initially(self, gm):
        await gm.set_goal("Explore")
        assert not gm.is_complete

    async def test_complete_after_all_done(self, gm):
        await gm.set_goal("Teleport to 0 64 0")
        for _ in range(4):
            gm.mark_current_complete()
        assert gm.is_complete

    async def test_progress_format(self, gm):
        await gm.set_goal("Explore")
        p = gm.progress
        assert "Goal:" in p
        assert "○" in p
        assert "CURRENT" in p

    async def test_progress_completed(self, gm):
        await gm.set_goal("Explore")
        gm.mark_current_complete()
        assert "✓" in gm.progress

    async def test_root_description(self, gm):
        await gm.set_goal("Test goal")
        assert gm.root_description == "Test goal"

    async def test_root_description_empty(self):
        gm2 = GoalManager()
        assert gm2.root_description == ""

    async def test_sub_goal_count(self, gm):
        await gm.set_goal("Explore")
        assert gm.sub_goal_count == 8

    async def test_sub_goal_count_none(self):
        gm2 = GoalManager()
        assert gm2.sub_goal_count == 0

    async def test_mark_complete_none(self, gm):
        gm._current = None
        gm.mark_current_complete()  # no-op, shouldn't crash

    async def test_current_goal_all_done(self, gm):
        gm._current = None
        assert gm.current_goal == "All goals complete!"

    async def test_set_goal_replaces(self, gm):
        await gm.set_goal("Explore")
        c1 = gm.sub_goal_count
        await gm.set_goal("Build")
        assert gm.sub_goal_count != c1
