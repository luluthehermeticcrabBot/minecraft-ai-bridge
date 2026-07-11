"""Tests for the SelfPreservationLayer — reflex attack + find-food injection."""

from __future__ import annotations

import pytest

from minecraft_ai_bridge.bridge.goal_manager import GoalManager
from minecraft_ai_bridge.bridge.self_preservation import (
    PreservationConfig,
    SelfPreservationLayer,
)
from minecraft_ai_bridge.minecraft.observer import WorldState

# ── Lightweight fixtures (no real MCPQ server) ───────────────────────────


class FakeMemory:
    """In-memory stand-in for AgentMemory — records facts and actions."""

    def __init__(self) -> None:
        self.facts: list[str] = []
        self.actions: list[tuple[str, dict]] = []

    def remember_fact(self, fact: str) -> None:
        self.facts.append(fact)

    def record_action(self, action: str, result: dict) -> None:
        self.actions.append((action, result))


def _make_layer(mock_mc, *, config: PreservationConfig | None = None) -> SelfPreservationLayer:
    """Build a layer wired to a mock MCPQ client and a fresh goal manager."""
    gm = GoalManager(llm_client=None)
    gm._root = None  # ensure set_goal populates it
    memory = FakeMemory()
    return SelfPreservationLayer(
        mc=mock_mc,
        goal_manager=gm,
        memory=memory,
        config=config,
    )


def _world(health: float | None = 20.0, hunger: int | None = 20) -> WorldState:
    return WorldState(health=health, hunger=hunger)


# ── Reflex attack ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReflexAttack:
    async def test_no_reflex_on_first_observation(self, mock_mc):
        """Without a previous-health baseline, no reflex should fire."""
        layer = _make_layer(mock_mc)
        world = _world(health=10.0)
        result = await layer.evaluate(world)
        assert result is None  # no reflex, no prior baseline

    async def test_no_reflex_without_health_drop(self, mock_mc):
        """If health is stable, no reflex should fire."""
        layer = _make_layer(mock_mc)
        # Prime previous_health by running evaluate once at full health
        await layer.evaluate(_world(health=20.0))
        # Now evaluate at the same health — no drop
        result = await layer.evaluate(_world(health=20.0))
        assert result is None

    async def test_reflex_triggers_on_health_drop_with_mob(self, mock_mc):
        """Sudden health drop + mob nearby → reflex attack fires."""
        layer = _make_layer(mock_mc)
        # Prime baseline
        await layer.evaluate(_world(health=20.0))
        # Now a sudden drop, with a zombie configured nearby
        mock_mc.set_hostile_mobs(["zombie"])
        result = await layer.evaluate(_world(health=15.0))
        assert result is not None
        assert result.success is True
        assert result.action.value == "attack"

    async def test_no_reflex_on_drop_without_mobs(self, mock_mc):
        """Health drop alone (no mobs) should not trigger a reflex."""
        layer = _make_layer(mock_mc)
        await layer.evaluate(_world(health=20.0))
        # No hostile mobs configured — should not attack anything
        result = await layer.evaluate(_world(health=12.0))
        assert result is None

    async def test_small_health_drop_below_threshold(self, mock_mc):
        """A small drop (less than sudden_health_drop) shouldn't trigger."""
        layer = _make_layer(mock_mc)
        await layer.evaluate(_world(health=20.0))
        mock_mc.set_hostile_mobs(["zombie"])
        # Drop is 1.0 — below the default threshold of 1.5
        result = await layer.evaluate(_world(health=19.0))
        assert result is None

    async def test_reflex_disabled_via_config(self, mock_mc):
        """If enable_reflex_attack=False, the layer never reflex-attacks."""
        layer = _make_layer(
            mock_mc,
            config=PreservationConfig(enable_reflex_attack=False),
        )
        await layer.evaluate(_world(health=20.0))
        mock_mc.set_hostile_mobs(["zombie"])
        result = await layer.evaluate(_world(health=10.0))
        assert result is None


# ── Find-food injection ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFindFoodInjection:
    def _gm_with_one_subgoal(self) -> GoalManager:
        from minecraft_ai_bridge.llm.models import AgentGoal

        gm = GoalManager(llm_client=None)
        gm._root = AgentGoal(description="parent", depth=0)
        return gm

    async def test_no_injection_when_hunger_fine(self, mock_mc):
        layer = _make_layer(mock_mc)
        layer._goals = self._gm_with_one_subgoal()
        await layer.evaluate(_world(hunger=20))
        # No sub-goal was injected
        assert len(layer._goals._root.sub_goals) == 0

    async def test_injection_when_hunger_critical(self, mock_mc):
        layer = _make_layer(mock_mc)
        layer._goals = self._gm_with_one_subgoal()
        await layer.evaluate(_world(hunger=3))
        assert len(layer._goals._root.sub_goals) == 1
        sg = layer._goals._root.sub_goals[0]
        assert "food" in sg.description.lower()
        assert "URGENT" in sg.description

    async def test_no_double_injection(self, mock_mc):
        """A second low-hunger observation should not add a second find-food goal."""
        layer = _make_layer(mock_mc)
        layer._goals = self._gm_with_one_subgoal()
        await layer.evaluate(_world(hunger=3))
        await layer.evaluate(_world(hunger=2))
        assert len(layer._goals._root.sub_goals) == 1

    async def test_injection_respects_existing_food_goal(self, mock_mc):
        from minecraft_ai_bridge.llm.models import AgentGoal

        layer = _make_layer(mock_mc)
        gm = self._gm_with_one_subgoal()
        # Add a pre-existing find-food goal that's not yet completed
        existing = AgentGoal(description="Cook some food", depth=1)
        gm._root.sub_goals.append(existing)
        layer._goals = gm
        await layer.evaluate(_world(hunger=2))
        # Should not inject a second one
        assert len(layer._goals._root.sub_goals) == 1
        assert layer._goals._root.sub_goals[0].description == "Cook some food"

    async def test_injection_disabled_via_config(self, mock_mc):
        layer = _make_layer(
            mock_mc,
            config=PreservationConfig(enable_auto_find_food=False),
        )
        layer._goals = self._gm_with_one_subgoal()
        await layer.evaluate(_world(hunger=2))
        assert len(layer._goals._root.sub_goals) == 0


# ── Memory facts ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMemoryFacts:
    async def test_critical_health_records_fact(self, mock_mc):
        layer = _make_layer(mock_mc)
        memory = layer._memory  # type: ignore[attr-defined]
        await layer.evaluate(_world(health=3.0))
        assert any("health critical" in f.lower() for f in memory.facts)

    async def test_health_above_threshold_no_fact(self, mock_mc):
        layer = _make_layer(mock_mc)
        memory = layer._memory  # type: ignore[attr-defined]
        await layer.evaluate(_world(health=15.0))
        assert not any("health critical" in f.lower() for f in memory.facts)

    async def test_reflex_attack_records_fact(self, mock_mc):
        layer = _make_layer(mock_mc)
        memory = layer._memory  # type: ignore[attr-defined]
        await layer.evaluate(_world(health=20.0))
        mock_mc.set_hostile_mobs(["skeleton"])
        await layer.evaluate(_world(health=15.0))
        # Should record both the reflex attack fact and possibly the health fact
        assert any("reflex" in f.lower() for f in memory.facts)
        assert any("skeleton" in f.lower() for f in memory.facts)


# ── Goal manager integration ────────────────────────────────────────────


@pytest.mark.asyncio
class TestFindFoodFallbackPlan:
    """The find-food fallback plan in goal_manager should match food-related goals."""

    async def test_eat_food_matches(self):
        gm = GoalManager(llm_client=None)
        root = await gm.set_goal("Find some food to eat")
        # The injected find-food sub-goal should be present
        assert any("food" in sg.description.lower() for sg in root.sub_goals)

    async def test_starving_matches(self):
        gm = GoalManager(llm_client=None)
        root = await gm.set_goal("I'm starving — get me food")
        assert any("food" in sg.description.lower() for sg in root.sub_goals)

    async def test_get_bread_matches(self):
        gm = GoalManager(llm_client=None)
        root = await gm.set_goal("Get some bread")
        assert any("food" in sg.description.lower() for sg in root.sub_goals)

    async def test_cook_food_matches(self):
        gm = GoalManager(llm_client=None)
        root = await gm.set_goal("Cook some food")
        assert any("food" in sg.description.lower() for sg in root.sub_goals)
