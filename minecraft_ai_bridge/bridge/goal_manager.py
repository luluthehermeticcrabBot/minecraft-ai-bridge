"""Goal management — decompose high-level goals into executable sub-goals
and track progress through the task tree.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..llm.client import LLMClient
from ..llm.models import AgentGoal

logger = logging.getLogger(__name__)


# ── Hardcoded fallback decompositions for common goals ────────────────
# When the LLM fails to decompose (returns nothing or non-JSON), these
# keyword-matched plans provide a sensible step-by-step breakdown.
_FALLBACK_PLANS: list[tuple[re.Pattern, str, list[str]]] = [
    (
        re.compile(r"house|build|shelter|home|base", re.IGNORECASE),
        "Build a shelter",
        [
            "Check inventory for building materials",
            "Scan surroundings for a suitable flat location",
            "Gather wood by checking/equipping and chopping nearby trees",
            "Craft a crafting table if you don't have one",
            "Craft wooden planks from logs",
            "Build a flat 5x5 foundation (floor) with dirt or planks",
            "Build 4 walls (3 blocks high) around the foundation",
            "Add a roof (ceiling) with remaining blocks",
            "Place a door in one wall for access",
            "Add interior: crafting table, torches for lighting",
            "Admire the finished house and signal completion",
        ],
    ),
    (
        re.compile(r"diamond|ore|mine|dig|tunnel|excavate", re.IGNORECASE),
        "Mine for resources",
        [
            "Check inventory for tools (pickaxe, shovel)",
            "Craft a wooden pickaxe if needed",
            "Scan for nearby stone to craft stone pickaxe",
            "Teleport near a cave entrance or slope",
            "Break stone to gather cobblestone for better tools",
            "Craft a stone pickaxe",
            "Descend into a cave or tunnel down to find ores",
            "Mine visible coal and iron ore",
            "Craft a furnace and smelt iron ore into ingots",
            "Craft an iron pickaxe (mining level 2 — can break diamond)",
            "Continue mining at depth ~11 for diamond ore",
            "Check inventory and report findings",
        ],
    ),
    (
        re.compile(r"farm|wheat|crop|bread|food|hunger", re.IGNORECASE),
        "Set up a farm",
        [
            "Check inventory for seeds, tools, and water bucket",
            "Scan for a flat area near water",
            "Till soil with a hoe (craft one if needed)",
            "Plant seeds in the tilled soil",
            "Ensure adequate lighting for crops (torches)",
            "Fence the perimeter to protect crops",
            "Wait for crops to grow or craft bone meal to accelerate",
            "Harvest mature crops",
            "Replant seeds for continuous supply",
            "Craft food (bread, etc.) from harvested crops",
        ],
    ),
    (
        re.compile(r"craft.*table|enchant|enchanting|anvil|grindstone", re.IGNORECASE),
        "Set up a workshop",
        [
            "Check inventory for required materials",
            "Craft a crafting table if missing",
            "Place the crafting table in a convenient spot",
            "Craft a furnace for smelting",
            "Place the furnace near the crafting table",
            "Gather wood for chests",
            "Craft and place a chest for storage",
            "Organize resources into chests by category",
            "Signal workshop setup complete",
        ],
    ),
    (
        re.compile(r"explore|find|locate|scout|look|survey|map", re.IGNORECASE),
        "Explore the area",
        [
            "Check position and scan surroundings",
            "Pick a direction (e.g. north) and teleport a short distance",
            "Scan again and note biomes, landmarks, and resources",
            "Teleport further in the same direction, scanning periodically",
            "Note any interesting features (villages, caves, mountains)",
            "Change direction to cover new terrain",
            "Return to starting point",
            "Report notable findings",
        ],
    ),
]


class GoalManager:
    """Manages the agent's goal hierarchy.

    - Accepts a high-level goal string
    - Decomposes it into sub-goals (optionally using the LLM)
    - Tracks which sub-goal is active
    - Reports completion status
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_depth: int = 5,
    ) -> None:
        self._llm = llm_client
        self._max_depth = max_depth
        self._root: AgentGoal | None = None
        self._current: AgentGoal | None = None

    # ── Goal loading ─────────────────────────────────────────────────

    async def set_goal(self, description: str) -> AgentGoal:
        """Set a new goal, optionally decomposing it into sub-goals."""
        self._root = AgentGoal(
            description=description,
            priority=1,
            depth=0,
        )

        if self._llm:
            logger.info("Decomposing goal: %s", description)
            subgoals = await self._llm.decompose_goal(description)
            if subgoals:
                for sg_data in subgoals:
                    desc = sg_data.get("description", sg_data.get("desc", "Unknown sub-goal"))
                    sg = AgentGoal(
                        description=desc,
                        priority=sg_data.get("step", 0),
                        depth=1,
                        parent_goal=description,
                    )
                    self._root.sub_goals.append(sg)
                logger.info(
                    "Decomposed into %d sub-goals", len(self._root.sub_goals)
                )
                self._current = self._root.active_sub_goal or self._root
                return self._root
            else:
                logger.info("LLM returned no sub-goals; trying fallback decomposition.")
        else:
            logger.info("No LLM client for decomposition; trying fallback decomposition.")

        # Fallback: hardcoded keyword-matched decomposition
        self._fallback_decompose(description)

        self._current = self._root.active_sub_goal or self._root
        return self._root

    def _fallback_decompose(self, description: str) -> None:
        """Match the goal description against hardcoded plans.

        Falls back to a generic step-by-step plan when no keyword pattern
        matches.
        """
        for pattern, _name, steps in _FALLBACK_PLANS:
            if pattern.search(description):
                logger.info("Fallback plan matched: %s (%d steps)", _name, len(steps))
                break
        else:
            # Generic fallback for unrecognized goals
            steps = [
                f"Assess current situation — check inventory, position, and surroundings",
                f"Plan the first concrete step toward: {description}",
                f"Execute the planned action",
                f"Check progress and adjust approach if needed",
                f"Repeat until the goal is complete",
                f"Verify completion and report results",
            ]
            logger.info("No keyword match; using generic fallback plan.")

        for i, step_desc in enumerate(steps):
            self._root.sub_goals.append(
                AgentGoal(
                    description=step_desc,
                    priority=i + 1,
                    depth=1,
                    parent_goal=description,
                )
            )
        logger.info("Fallback decomposition: %d sub-goals", len(steps))

    def set_goal_from_subgoals(self, description: str, subgoals: list[dict[str, Any]]) -> AgentGoal:
        """Set a pre-decomposed goal (no LLM call)."""
        self._root = AgentGoal(description=description, depth=0)
        for i, sg in enumerate(subgoals):
            self._root.sub_goals.append(
                AgentGoal(
                    description=sg.get("description", f"Step {i+1}"),
                    priority=i + 1,
                    depth=1,
                    parent_goal=description,
                )
            )
        self._current = self._root.active_sub_goal or self._root
        return self._root

    # ── Progress tracking ────────────────────────────────────────────

    def mark_current_complete(self) -> None:
        """Mark the current sub-goal as done and advance to the next."""
        if self._current is None:
            return
        self._current.completed = True
        logger.info("Goal completed: %s", self._current.description)

        if self._current.parent_goal:
            # Find next sibling
            parent = self._root
            siblings = parent.sub_goals
            idx = next(
                (i for i, sg in enumerate(siblings) if sg is self._current),
                -1,
            )
            if idx + 1 < len(siblings):
                self._current = siblings[idx + 1]
            else:
                parent.completed = True
                self._current = None  # all done
        else:
            self._current = None

    @property
    def current_goal(self) -> str:
        """Human-readable current goal description."""
        if self._current is None:
            return "All goals complete!"
        return self._current.description

    @property
    def is_complete(self) -> bool:
        """All goals are finished."""
        return self._current is None and (self._root is not None and self._root.completed)

    @property
    def progress(self) -> str:
        """Summary of goal progress for the LLM prompt."""
        if self._root is None:
            return "No goal set."
        lines = [f"=== Goal: {self._root.description} ==="]
        if not self._root.sub_goals:
            lines.append("Status: in progress")
            return "\n".join(lines)
        for i, sg in enumerate(self._root.sub_goals, 1):
            status = "✓" if sg.completed else "○"
            active = " ← CURRENT" if sg is self._current else ""
            lines.append(f"  {status} {sg.description}{active}")
        if self._current is None and not self._root.completed:
            lines.append("  → All sub-goals complete!")
        return "\n".join(lines)
