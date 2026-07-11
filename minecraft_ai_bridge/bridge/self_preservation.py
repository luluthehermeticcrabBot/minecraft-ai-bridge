"""Self-preservation layer — runs after observation, before the LLM thinks.

The orchestrator's main loop is LLM-driven: the model sees the world
state, decides what action to take, and the bridge executes it.  That
works for deliberate planning but has a latency problem for reflex
behaviours.  If a hostile mob walks up and hits the player, waiting
for the LLM to "ponder on what to do" can mean taking several more
hits before the agent responds.

This layer fills that gap.  After each observation cycle, it makes a
few cheap checks and either:

* **Reflex attack** — if the player's health just dropped and a hostile
  mob is nearby, attack it *immediately* without round-tripping
  through the LLM.  This is the "surprise attack" handler.
* **Find-food injection** — if hunger is critically low and no
  find-food sub-goal is already pending, inject one at the front of
  the goal list so it becomes the LLM's next task.
* **Memory fact** — if health is critical, record a fact so the LLM
  sees the warning in its context on the next turn.

The layer is opt-in via ``PreservationConfig`` and never blocks the
LLM from running — it can only inject an action result, never
silently swallow one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..llm.models import AgentGoal
from ..minecraft.actions import ActionResult, ActionType, execute_action
from ..minecraft.mc_api import McpqClient
from ..minecraft.observer import WorldState

if TYPE_CHECKING:
    from .goal_manager import GoalManager
    from .memory import AgentMemory

logger = logging.getLogger(__name__)


@dataclass
class PreservationConfig:
    """Tuning knobs for the self-preservation layer.

    All thresholds are in Minecraft units (health and hunger are
    0-20 each; a sudden health drop is in HP lost between turns).
    """

    # When health drops below this, log a memory fact so the LLM sees it.
    health_critical_threshold: float = 4.0
    # When hunger drops below this, inject a "find food" sub-goal.
    hunger_critical_threshold: int = 6
    # How far to scan for hostile mobs when looking for a reflex target.
    mob_alert_radius: int = 5
    # Minimum health drop (HP) in one turn to trigger a reflex attack.
    sudden_health_drop: float = 1.5
    # Damage amount for reflex attacks. 8 = 4 hearts — enough to scare
    # most mobs but not enough to one-shot a creeper next to the player.
    reflex_damage: int = 8
    # Feature flags
    enable_reflex_attack: bool = True
    enable_auto_find_food: bool = True


class SelfPreservationLayer:
    """Inserts reflex actions and urgent sub-goals between observe and think.

    Owned by the :class:`Orchestrator`.  Single instance per agent run
    so it can track the previous-turn health for surprise-attack
    detection.

    Usage from the orchestrator::

        reflex = await self._preservation.evaluate(world)
        if reflex is not None:
            result = reflex           # skip the LLM this turn
        else:
            ...                        # normal LLM-driven flow
    """

    def __init__(
        self,
        mc: McpqClient,
        goal_manager: GoalManager,
        memory: AgentMemory,
        config: PreservationConfig | None = None,
    ) -> None:
        self._mc = mc
        self._goals = goal_manager
        self._memory = memory
        self._config = config or PreservationConfig()
        # Last seen health — used to detect sudden drops. None means
        # the first observation hasn't happened yet.
        self._previous_health: float | None = None

    async def evaluate(self, world: WorldState) -> ActionResult | None:
        """Run the preservation checks against the latest world state.

        Returns an :class:`ActionResult` if the layer wants to act
        immediately (suppressing the LLM for this turn), or ``None``
        to defer to normal LLM-driven flow.
        """
        if not self._config.enable_reflex_attack and not self._config.enable_auto_find_food:
            return None

        # Reflex attack takes priority — if we're getting hit, fight
        # first, worry about food second.
        reflex: ActionResult | None = None
        if self._config.enable_reflex_attack:
            reflex = await self._maybe_reflex_attack(world)

        # Auto-injection happens regardless of whether we acted above —
        # the LLM still gets to think on the next turn.
        if self._config.enable_auto_find_food:
            self._maybe_inject_find_food(world)

        # Memory hint for the LLM context window.
        if world.health is not None and world.health < self._config.health_critical_threshold:
            self._memory.remember_fact(f"Health critical: {world.health}/20 — find safety or heal")

        # Track health for next-turn drop detection. We do this after
        # the reflex logic so the drop is measured against the previous
        # turn's value, not the one we just observed.
        if world.health is not None:
            self._previous_health = world.health

        return reflex

    async def _maybe_reflex_attack(self, world: WorldState) -> ActionResult | None:
        """If health just dropped and a hostile mob is in range, attack it.

        "Just dropped" means the current health is at least
        ``sudden_health_drop`` HP below the previous turn's health.
        This avoids triggering on the first observation (no previous
        baseline) and on natural regeneration (which is gradual).
        """
        if self._previous_health is None or world.health is None:
            return None
        drop = self._previous_health - world.health
        if drop < self._config.sudden_health_drop:
            return None

        # We took a hit — look for something to hit back.
        scan = await execute_action(
            self._mc,
            ActionType.SCAN_ENTITIES,
            {"radius": self._config.mob_alert_radius},
        )
        if not scan.success:
            return None
        mobs: list[str] = scan.data.get("mobs_nearby", [])
        if not mobs:
            return None

        # Attack the first detected mob. The LLM will still see the
        # result and can decide whether to continue or flee.
        target = mobs[0]
        attack = await execute_action(
            self._mc,
            ActionType.ATTACK,
            {
                "entity_type": target,
                "damage_amount": self._config.reflex_damage,
            },
        )
        if attack.success:
            self._memory.remember_fact(
                f"Reflexive attack on {target} after health drop of {drop:.1f} HP"
            )
            logger.info("Reflex attack on %s (health dropped %.1f HP)", target, drop)
        return attack

    def _maybe_inject_find_food(self, world: WorldState) -> None:
        """Inject a high-priority 'find food' sub-goal when hunger is low.

        The new sub-goal is inserted at the FRONT of the goal list so
        the GoalManager's active_sub_goal (which returns the first
        incomplete sub-goal) will surface it on the next turn.  We
        skip injection if a find-food sub-goal is already pending so
        we don't pollute the goal tree with duplicates.
        """
        if world.hunger is None or world.hunger >= self._config.hunger_critical_threshold:
            return

        root = self._goals._root
        if root is None:
            return

        for sg in root.sub_goals:
            if "food" in sg.description.lower() and not sg.completed:
                return  # already pending

        new_goal = AgentGoal(
            description="URGENT: Find and eat food (hunger is critical)",
            priority=0,
            depth=1,
            parent_goal="self-preservation",
        )
        new_goal._parent_ref = root
        root.sub_goals.insert(0, new_goal)
        self._memory.remember_fact(
            f"Hunger critical: {world.hunger}/20 — injected find-food sub-goal"
        )
        logger.info("Injected URGENT find-food sub-goal (hunger=%d)", world.hunger)
