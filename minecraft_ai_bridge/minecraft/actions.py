"""Action primitives the LLM can invoke inside Minecraft.

Each action maps to one or more MCPQ plugin operations (or RCON commands
as a fallback), allowing the agent to observe and interact with the world.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .mc_api import McpqClient

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Every action the LLM can take.  Keep this list concise so the
    LLM's action space stays manageable."""

    # ── Movement ────────────────────────────────────────────────────
    MOVE_TO = "move_to"
    MOVE_FORWARD = "move_forward"
    MOVE_BACK = "move_back"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    JUMP = "jump"
    TELEPORT = "teleport"

    # ── Interaction ─────────────────────────────────────────────────
    BREAK_BLOCK = "break_block"
    PLACE_BLOCK = "place_block"
    INTERACT = "interact"

    # ── Inventory / Items ───────────────────────────────────────────
    CHECK_INVENTORY = "check_inventory"
    EQUIP_ITEM = "equip_item"
    CRAFT_ITEM = "craft_item"
    DROP_ITEM = "drop_item"

    # ── Combat ──────────────────────────────────────────────────────
    ATTACK = "attack"

    # ── Information ─────────────────────────────────────────────────
    SCAN = "scan"
    CHECK_TIME = "check_time"
    CHECK_WEATHER = "check_weather"
    CHECK_HEALTH = "check_health"
    CHECK_POSITION = "check_position"
    LIST_PLAYERS = "list_players"

    # ── Communication ───────────────────────────────────────────────
    CHAT = "chat"

    # ── Meta ────────────────────────────────────────────────────────
    WAIT = "wait"
    DONE = "done"  # signal sub-goal / goal completion


@dataclass
class ActionResult:
    """Result of executing a single action."""

    success: bool
    action: ActionType
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ── Action execution ────────────────────────────────────────────────────

# Handlers now receive an McpqClient instead of RCONClient.  MCPQ gives
# direct world-manipulation and player-control APIs — much richer than
# what was possible through RCON commands alone.


async def execute_action(
    mc: McpqClient,
    action_type: ActionType,
    params: dict[str, Any] | None = None,
) -> ActionResult:
    """Dispatch an action to its handler and return the result.

    Parameters
    ----------
    mc : connected MCPQ client
    action_type : which action to perform
    params : action-specific parameters (see each handler)
    """
    params = params or {}
    handler = _HANDLERS.get(action_type)
    if handler is None:
        return ActionResult(
            success=False,
            action=action_type,
            message=f"No handler registered for {action_type.value}",
        )
    try:
        return await handler(mc, params)
    except Exception as exc:
        logger.exception("Action %s failed", action_type.value)
        return ActionResult(
            success=False,
            action=action_type,
            message=f"Error: {exc}",
        )


# ── Individual action handlers ─────────────────────────────────────────

Handler = callable  # type: ignore[type-arg]


async def _cmd(mc: McpqClient, cmd: str) -> str:
    """Run a command and return stripped response."""
    raw = await mc.run_command_blocking(cmd)
    return raw.strip()


# ── Movement ────────────────────────────────────────────────────────────


async def _move_to(mc: McpqClient, params: dict) -> ActionResult:
    x = params.get("x", 0)
    y = params.get("y", 0)
    z = params.get("z", 0)
    await mc.teleport_player(x, y, z)
    return ActionResult(
        success=True,
        action=ActionType.MOVE_TO,
        message=f"Teleported to ({x}, {y}, {z})",
        data={"x": x, "y": y, "z": z},
    )


async def _move_forward(mc: McpqClient, params: dict) -> ActionResult:
    steps = params.get("steps", 2)
    resp = await _cmd(mc, f"tp @p ^ ^ ^{steps}")
    return ActionResult(
        success=True,
        action=ActionType.MOVE_FORWARD,
        message=f"Moved forward {steps} blocks",
        data={"steps": steps, "response": resp},
    )


async def _move_back(mc: McpqClient, params: dict) -> ActionResult:
    steps = params.get("steps", 2)
    resp = await _cmd(mc, f"tp @p ^ ^ ^-{steps}")
    return ActionResult(
        success=True,
        action=ActionType.MOVE_BACK,
        message=f"Moved back {steps} blocks",
        data={"steps": steps, "response": resp},
    )


async def _turn_left(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "tp @p ~ ~ ~-90 ~")
    return ActionResult(
        success=True,
        action=ActionType.TURN_LEFT,
        message="Turned left",
        data={"response": resp},
    )


async def _turn_right(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "tp @p ~ ~ ~90 ~")
    return ActionResult(
        success=True,
        action=ActionType.TURN_RIGHT,
        message="Turned right",
        data={"response": resp},
    )


async def _jump(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "tp @p ~ ~1 ~")
    return ActionResult(
        success=True,
        action=ActionType.JUMP,
        message="Jumped",
        data={"response": resp},
    )


async def _teleport(mc: McpqClient, params: dict) -> ActionResult:
    return await _move_to(mc, params)


# ── Interaction ─────────────────────────────────────────────────────────


async def _break_block(mc: McpqClient, params: dict) -> ActionResult:
    x = params.get("x")
    y = params.get("y")
    z = params.get("z")
    if x is not None and y is not None and z is not None:
        await mc.set_block("air", int(x), int(y), int(z))
        msg = f"Broke block at ({x}, {y}, {z})"
    else:
        # Break block player is looking at (relative ~ ~ ~1)
        resp = await _cmd(mc, "setblock ~ ~ ~1 air destroy")
        msg = "Attempted to break targeted block"
        if "Changed the block" not in resp:
            msg = f"Could not break targeted block: {resp[:80]}"
    return ActionResult(
        success=True,
        action=ActionType.BREAK_BLOCK,
        message=msg,
    )


async def _place_block(mc: McpqClient, params: dict) -> ActionResult:
    x = params.get("x")
    y = params.get("y")
    z = params.get("z")
    block_type = params.get("block_type", "stone")
    try:
        if x is not None and y is not None and z is not None:
            await mc.set_block(block_type, int(x), int(y), int(z))
            msg = f"Placed {block_type} at ({x}, {y}, {z})"
        else:
            # Place in front of player
            resp = await _cmd(mc, f"setblock ~ ~ ~1 {block_type}")
            msg = f"Placed {block_type} in front"
            if "Changed the block" not in resp and "block changed" not in resp:
                msg = f"Place result: {resp[:80]}"
        return ActionResult(success=True, action=ActionType.PLACE_BLOCK, message=msg)
    except Exception as exc:
        return ActionResult(success=False, action=ActionType.PLACE_BLOCK, message=str(exc))


async def _interact(mc: McpqClient, params: dict) -> ActionResult:
    # Use /execute as @p run interact — works on Paper
    resp = await _cmd(mc, "execute as @p at @p run interact")
    return ActionResult(
        success=True,
        action=ActionType.INTERACT,
        message="Interacted",
        data={"response": resp},
    )


# ── Inventory / Items ───────────────────────────────────────────────────


async def _check_inventory(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "data get entity @p Inventory")
    return ActionResult(
        success=True,
        action=ActionType.CHECK_INVENTORY,
        message="Retrieved inventory",
        data={"raw_inventory": resp},
    )


async def _equip_item(mc: McpqClient, params: dict) -> ActionResult:
    slot = params.get("slot", 0)
    resp = await _cmd(mc, f"item replace entity @p hotbar.0 with entity @p hotbar.{slot}")
    return ActionResult(
        success=True,
        action=ActionType.EQUIP_ITEM,
        message=f"Equipped item from slot {slot}",
        data={"slot": slot, "response": resp},
    )


async def _craft_item(mc: McpqClient, params: dict) -> ActionResult:
    item = params.get("item_type", "crafting_table")
    amount = params.get("amount", 1)
    resp = await _cmd(mc, f"give @p {item} {amount}")
    return ActionResult(
        success=True,
        action=ActionType.CRAFT_ITEM,
        message=f"Gave {amount}x {item}",
        data={"item": item, "amount": amount, "response": resp},
    )


async def _drop_item(mc: McpqClient, params: dict) -> ActionResult:
    item = params.get("item_type", "stone")
    amount = params.get("amount", 1)
    resp = await _cmd(mc, f"clear @p {item} {amount}")
    # Then drop the cleared items via /replaceitem... actually just use clear
    # The actual "drop" would be: /execute as @p run clear @p <item> <amount>
    return ActionResult(
        success=True,
        action=ActionType.DROP_ITEM,
        message=f"Removed {amount}x {item} from inventory",
        data={"item": item, "amount": amount, "response": resp},
    )


# ── Combat ──────────────────────────────────────────────────────────────


async def _attack(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "execute as @p at @p run attack")
    return ActionResult(
        success=True,
        action=ActionType.ATTACK,
        message="Attacked",
        data={"response": resp},
    )


# ── Information ─────────────────────────────────────────────────────────


async def _scan(mc: McpqClient, params: dict) -> ActionResult:
    radius = min(params.get("radius", 5), 16)  # cap at 16 to avoid spam

    # Get player position first
    pos = await mc.get_player_pos()
    data: dict[str, Any] = {"radius": radius}

    if pos:
        px, py, pz = int(pos[0]), int(pos[1]), int(pos[2])
        data["position"] = [px, py, pz]

        # Scan blocks around the player (3×3 at feet level, plus above/below)
        nearby: dict[str, str] = {}
        try:
            # Key reference blocks
            nearby["block_feet"] = await mc.get_block(px, py - 1, pz)
            nearby["block_head"] = await mc.get_block(px, py + 1, pz)

            # Front/back/left/right at feet level
            nearby["north"] = await mc.get_block(px, py - 1, pz - 1)
            nearby["south"] = await mc.get_block(px, py - 1, pz + 1)
            nearby["east"]  = await mc.get_block(px + 1, py - 1, pz)
            nearby["west"]  = await mc.get_block(px - 1, py - 1, pz)

            # What's directly in front at eye level
            nearby["front_eye"] = await mc.get_block(px, py, pz + 1)
        except Exception:
            pass

        data["nearby"] = nearby

        # Scan visible blocks in the radius (sample at cardinal points)
        if radius >= 3:
            sample: dict[str, str] = {}
            try:
                for dx, dz in [(0, 2), (2, 0), (0, -2), (-2, 0),
                               (2, 2), (2, -2), (-2, 2), (-2, -2)]:
                    key = f"d{dx:+}z{dz:+}"
                    sample[key] = await mc.get_block(
                        px + dx, py - 1, pz + dz
                    )
            except Exception:
                pass
            data["sample"] = sample

        # Note: biome detection omitted — the /locate biome command
        # produces noisy error output that clutters the LLM prompt.
    else:
        data["note"] = "Player position unavailable"

    # Gather time / weather / players
    try:
        data["time"] = await mc.get_time()
        data["players"] = await mc.get_players_online()
    except Exception:
        pass

    return ActionResult(
        success=True,
        action=ActionType.SCAN,
        message=f"Scanned surroundings (r={radius})",
        data=data,
    )


async def _check_time(mc: McpqClient, params: dict) -> ActionResult:
    resp = await mc.get_time()
    return ActionResult(
        success=True,
        action=ActionType.CHECK_TIME,
        message="Time checked",
        data={"time_raw": resp},
    )


async def _check_weather(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "weather query")
    return ActionResult(
        success=True,
        action=ActionType.CHECK_WEATHER,
        message="Weather checked",
        data={"weather_raw": resp},
    )


async def _check_health(mc: McpqClient, params: dict) -> ActionResult:
    resp = await _cmd(mc, "data get entity @p Health")
    return ActionResult(
        success=True,
        action=ActionType.CHECK_HEALTH,
        message="Health checked",
        data={"health_raw": resp},
    )


async def _check_position(mc: McpqClient, params: dict) -> ActionResult:
    pos = await mc.get_player_pos()
    if pos:
        msg = f"Position: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})"
    else:
        msg = "Could not get player position"
        pos = (0, 0, 0)
    return ActionResult(
        success=True,
        action=ActionType.CHECK_POSITION,
        message=msg,
        data={"position_raw": f"[{pos[0]}d, {pos[1]}d, {pos[2]}d]"},
    )


async def _list_players(mc: McpqClient, params: dict) -> ActionResult:
    players = await mc.get_players_online()
    msg = f"Online players ({len(players)}): {', '.join(players)}"
    return ActionResult(
        success=True,
        action=ActionType.LIST_PLAYERS,
        message=msg,
        data={"players": players},
    )


async def _chat(mc: McpqClient, params: dict) -> ActionResult:
    message = params.get("message", "")
    if message:
        await mc.post_to_chat(message)
    return ActionResult(
        success=True,
        action=ActionType.CHAT,
        message=f'Said: "{message}"',
        data={"message": message},
    )


async def _wait(mc: McpqClient, params: dict) -> ActionResult:
    import asyncio as _asyncio
    seconds = params.get("seconds", 2.0)
    await _asyncio.sleep(seconds)
    return ActionResult(
        success=True,
        action=ActionType.WAIT,
        message=f"Waited {seconds}s",
        data={"seconds": seconds},
    )


async def _done(mc: McpqClient, params: dict) -> ActionResult:
    message = params.get("message", "Task complete")
    return ActionResult(
        success=True,
        action=ActionType.DONE,
        message=message,
        data={"completion_message": message},
    )


# ── Handler registry ────────────────────────────────────────────────────

_HANDLERS: dict[ActionType, Handler] = {
    ActionType.MOVE_TO: _move_to,
    ActionType.MOVE_FORWARD: _move_forward,
    ActionType.MOVE_BACK: _move_back,
    ActionType.TURN_LEFT: _turn_left,
    ActionType.TURN_RIGHT: _turn_right,
    ActionType.JUMP: _jump,
    ActionType.TELEPORT: _teleport,
    ActionType.BREAK_BLOCK: _break_block,
    ActionType.PLACE_BLOCK: _place_block,
    ActionType.INTERACT: _interact,
    ActionType.CHECK_INVENTORY: _check_inventory,
    ActionType.EQUIP_ITEM: _equip_item,
    ActionType.CRAFT_ITEM: _craft_item,
    ActionType.DROP_ITEM: _drop_item,
    ActionType.ATTACK: _attack,
    ActionType.SCAN: _scan,
    ActionType.CHECK_TIME: _check_time,
    ActionType.CHECK_WEATHER: _check_weather,
    ActionType.CHECK_HEALTH: _check_health,
    ActionType.CHECK_POSITION: _check_position,
    ActionType.LIST_PLAYERS: _list_players,
    ActionType.CHAT: _chat,
    ActionType.WAIT: _wait,
    ActionType.DONE: _done,
}
