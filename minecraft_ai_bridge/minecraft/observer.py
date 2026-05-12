"""World observation — translates MCPQ plugin data into structured state.

The observer provides the LLM with a high-level view of the world:
- Player position, health, inventory
- Time of day, weather
- Notable events (e.g., damage taken, mobs nearby)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .actions import ActionType, ActionResult, execute_action
from .mc_api import McpqClient

logger = logging.getLogger(__name__)


@dataclass
class WorldState:
    """Snapshot of the player's current world state."""

    position: tuple[float, float, float] | None = None
    health: float | None = None
    inventory_raw: str = ""
    time_raw: str = ""
    weather_raw: str = ""
    players: list[str] = field(default_factory=list)
    scan_data: dict[str, Any] = field(default_factory=dict)
    last_action_result: str = ""


class Observer:
    """Collects structured observations from the MCPQ plugin.

    Uses the action system internally so all observation paths go through
    the same action-execution layer.
    """

    def __init__(self, mc: McpqClient) -> None:
        self._mc = mc

    async def observe(self) -> WorldState:
        """Gather a full state snapshot.  Returns a ``WorldState``."""
        state = WorldState()

        # Run several observation actions concurrently-ish
        results = await asyncio.gather(
            self._exec(ActionType.CHECK_POSITION),
            self._exec(ActionType.CHECK_HEALTH),
            self._exec(ActionType.CHECK_INVENTORY),
            self._exec(ActionType.CHECK_TIME),
            self._exec(ActionType.LIST_PLAYERS),
            return_exceptions=True,
        )

        pos_res, health_res, inv_res, time_res, players_res = results

        if isinstance(pos_res, ActionResult) and pos_res.success:
            raw = pos_res.data.get("position_raw", "")
            parsed = _parse_nbt_list(raw)
            if parsed and len(parsed) == 3:
                state.position = (parsed[0], parsed[1], parsed[2])

        if isinstance(health_res, ActionResult) and health_res.success:
            raw = health_res.data.get("health_raw", "")
            state.health = _parse_nbt_value(raw)

        if isinstance(inv_res, ActionResult) and inv_res.success:
            state.inventory_raw = inv_res.data.get("raw_inventory", "")

        if isinstance(time_res, ActionResult) and time_res.success:
            state.time_raw = time_res.data.get("time_raw", "")

        if isinstance(players_res, ActionResult) and players_res.success:
            state.players = players_res.data.get("players", [])

        # Also do a quick scan
        scan_res = await self._exec(ActionType.SCAN, {"radius": 5})
        if isinstance(scan_res, ActionResult) and scan_res.success:
            state.scan_data = scan_res.data

        return state

    async def observe_position(self) -> tuple[float, float, float] | None:
        """Quick position-only check."""
        return await self._mc.get_player_pos()

    async def _exec(
        self, action: ActionType, params: dict | None = None
    ) -> ActionResult:
        return await execute_action(self._mc, action, params)


# ── Simple NBT-value parsers (for command output) ──────────────────────

import re  # noqa: E402 — import after class uses

_NBT_LIST_RE = re.compile(r"\[([^\]]+)\]")
_NBT_VALUE_RE = re.compile(r"(-?\d+\.?\d*)[dfbsIL]?")


def _parse_nbt_value(raw: str) -> Any:
    """Try to extract a single numeric value from an NBT-encoded string."""
    raw = raw.strip()
    if not raw:
        return None
    m = _NBT_VALUE_RE.search(raw)
    if m:
        val = m.group(1)
        if "." in val:
            return float(val)
        return int(float(val))
    return raw


def _parse_nbt_list(raw: str) -> list[float] | None:
    """Parse something like ``[1.0d, 64.0d, 3.0d]`` into ``[1.0, 64.0, 3.0]``."""
    m = _NBT_LIST_RE.search(raw)
    if not m:
        return None
    parts = m.group(1).split(",")
    out: list[float] = []
    for p in parts:
        val = _parse_nbt_value(p.strip())
        if isinstance(val, (int, float)):
            out.append(float(val))
    return out if out else None
