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

from .actions import ActionResult, ActionType, execute_action
from .mc_api import McpqClient

logger = logging.getLogger(__name__)


@dataclass
class InventorySlot:
    """A single item stack in the player's inventory."""

    item_id: str
    count: int
    slot: int
    damage: int = 0

    @property
    def display_name(self) -> str:
        """Human-readable item name (strip Minecraft namespace)."""
        return self.item_id.replace("minecraft:", "").replace("_", " ")


@dataclass
class WorldState:
    """Snapshot of the player's current world state."""

    position: tuple[float, float, float] | None = None
    health: float | None = None
    inventory_raw: str = ""
    inventory: list[InventorySlot] = field(default_factory=list)
    time_raw: str = ""
    weather_raw: str = ""
    players: list[str] = field(default_factory=list)
    biome: str = ""
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
            state.inventory = _parse_inventory_nbt(state.inventory_raw)

        if isinstance(time_res, ActionResult) and time_res.success:
            state.time_raw = time_res.data.get("time_raw", "")

        if isinstance(players_res, ActionResult) and players_res.success:
            state.players = players_res.data.get("players", [])

        # Also do a quick scan
        scan_res = await self._exec(ActionType.SCAN, {"radius": 5})
        if isinstance(scan_res, ActionResult) and scan_res.success:
            state.scan_data = scan_res.data

        # Best-effort biome detection
        if state.position:
            try:
                state.biome = await self._mc.get_biome(
                    int(state.position[0]),
                    int(state.position[1]),
                    int(state.position[2]),
                )
            except Exception:
                pass

        return state

    async def observe_position(self) -> tuple[float, float, float] | None:
        """Quick position-only check."""
        return await self._mc.get_player_pos()

    async def _exec(self, action: ActionType, params: dict | None = None) -> ActionResult:
        return await execute_action(self._mc, action, params)


# ── Simple NBT-value parsers (for command output) ──────────────────────

import json  # noqa: E402
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


def _parse_inventory_nbt(raw: str) -> list[InventorySlot]:
    """Parse raw NBT inventory string into structured InventorySlot list.

    Handles formats like::
        [{id:"minecraft:dirt",Count:64b,Slot:0b},{id:"minecraft:stone",Count:32b,Slot:1b}]

    Returns an empty list on any parse failure (callers should fall back
    to the raw string).
    """
    if not raw or raw == "Inventory: []":
        return []

    # Normalise: convert JSON-like NBT to proper JSON
    text = raw.strip()
    if text.startswith("Inventory: "):
        text = text[len("Inventory: ") :]

    text = text.replace("}", "},")
    # Remove trailing comma from array
    text = text.rstrip(",")

    # Try a simple regex-based approach first (faster for well-formed data)
    items: list[InventorySlot] = []
    # Pattern: {id:"...",Count:...b,Slot:...b,...}
    item_pattern = re.compile(
        r'id:\s*"([^"]+)"\s*,\s*'
        r"Count:\s*(\d+)\s*b\s*,\s*"
        r"Slot:\s*(-?\d+)\s*b",
    )
    for match in item_pattern.finditer(raw):
        items.append(
            InventorySlot(
                item_id=match.group(1),
                count=int(match.group(2)),
                slot=int(match.group(3)),
            )
        )

    # If regex found items, return them
    if items:
        return items

    # Fallback: try JSON parsing (for simulators / test data)
    try:
        # Convert NBT-style booleans and byte suffixes to JSON
        clean = text
        # Remove trailing 'b' from numbers
        clean = re.sub(r"(\d+)b", r"\1", clean)
        # Quote bare keys
        clean = re.sub(r"(\w+):", r'"\1":', clean)
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            for entry in parsed:
                items.append(
                    InventorySlot(
                        item_id=entry.get("id", "unknown"),
                        count=int(entry.get("Count", 1)),
                        slot=int(entry.get("Slot", 0)),
                    )
                )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    return items


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
