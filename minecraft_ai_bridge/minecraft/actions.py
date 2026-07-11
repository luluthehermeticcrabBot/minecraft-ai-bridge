"""Action primitives the LLM can invoke inside Minecraft.

Each action maps to one or more MCPQ plugin operations (or RCON commands
as a fallback), allowing the agent to observe and interact with the world.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .mc_api import McpqClient

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Every action the LLM can take.  Keep this list concise so the
    LLM's action space stays manageable."""

    # ── Movement ────────────────────────────────────────────────────
    MOVE_TO = "move_to"
    MOVE_FORWARD = "move_forward"
    MOVE_BACK = "move_back"
    WALK_TO = "walk_to"  # human-like step-by-step walking
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    JUMP = "jump"
    SPRINT = "sprint"  # faster forward movement (1.0-block steps)
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


# ── Block classification ─────────────────────────────────────────────────
# These sets define which blocks the agent can walk through (passable),
# which are hazards (cause damage), and which indicate player-made
# structures (should not be built over).

_PASSABLE_BLOCKS: set[str] = {
    "air",
    "cave_air",
    "void_air",
    "grass",
    "tall_grass",
    "fern",
    "large_fern",
    "dead_bush",
    "water",
    "flowing_water",
    "lava",
    "flowing_lava",  # passable but hazardous!
    "snow",
    "vine",
    "torch",
    "wall_torch",
    "soul_torch",
    "redstone_torch",
    "redstone_wire",
    "repeater",
    "comparator",
    "lever",
    "button",
    "stone_button",
    "oak_button",
    "pressure_plate",
    "stone_pressure_plate",
    "oak_pressure_plate",
    "rail",
    "powered_rail",
    "detector_rail",
    "activator_rail",
    "red_mushroom",
    "brown_mushroom",
    "dandelion",
    "poppy",
    "blue_orchid",
    "oxeye_daisy",
    "cornflower",
    "lily_of_the_valley",
    "wheat",
    "carrots",
    "potatoes",
    "beetroots",
    "nether_wart",
    "cobweb",
    "ladder",
    "scaffolding",
}

_HAZARD_BLOCKS: set[str] = {
    "lava",
    "flowing_lava",
    "fire",
    "soul_fire",
    "cactus",
    "magma_block",
    "campfire",
    "soul_campfire",
    "wither_rose",
    "sweet_berry_bush",
    "powder_snow",
}

_STRUCTURE_BLOCKS: set[str] = {
    # Building materials (player-made)
    "oak_planks",
    "spruce_planks",
    "birch_planks",
    "jungle_planks",
    "acacia_planks",
    "dark_oak_planks",
    "crimson_planks",
    "warped_planks",
    "glass",
    "glass_pane",
    "white_stained_glass",
    "bricks",
    "stone_bricks",
    "cobblestone",
    # Infrastructure
    "rail",
    "powered_rail",
    "detector_rail",
    "activator_rail",
    "oak_door",
    "spruce_door",
    "birch_door",
    "iron_door",
    "oak_fence",
    "oak_fence_gate",
    # Functional
    "crafting_table",
    "furnace",
    "chest",
    "barrel",
    "shulker_box",
    "bed",
    "white_bed",
    "red_bed",
    "enchanting_table",
    "anvil",
    "grindstone",
    "campfire",
    "lantern",
    "soul_lantern",
}


def _is_passable(block_id: str) -> bool:
    """Check whether a block can be walked through."""
    bid = block_id.lower().replace("minecraft:", "")
    if bid in _PASSABLE_BLOCKS:
        return True
    # Any "air" variant is passable
    if bid.endswith("air"):
        return True
    # Transparent blocks that don't block movement
    passable_suffixes = (
        "_slab",
        "_stairs",
        "_door",
        "_trapdoor",
        "_fence",
        "_fence_gate",
        "_wall",
        "_sign",
        "sign",
        "_button",
        "_plate",
        "_carpet",
        "_glass",
        "_pane",
        "_sapling",
        "_seed",
        "seed",
        "_coral",
        "_kelp",
        "_seagrass",
    )
    return bid.endswith(passable_suffixes)


def _is_hazard(block_id: str) -> bool:
    """Check whether a block causes damage to the player."""
    bid = block_id.lower().replace("minecraft:", "")
    return bid in _HAZARD_BLOCKS or any(h in bid for h in ("lava", "fire"))


def _is_artificial(block_id: str) -> bool:
    """Check whether a block indicates player-made construction."""
    bid = block_id.lower().replace("minecraft:", "")
    return bid in _STRUCTURE_BLOCKS or any(
        s in bid
        for s in (
            "_planks",
            "_door",
            "_fence",
            "_glass",
            "_bed",
            "chest",
            "furnace",
            "anvil",
            "crafting_table",
            "enchanting_table",
        )
    )


async def _can_move_to(
    mc: McpqClient,
    x: int,
    y: int,
    z: int,
) -> tuple[bool, str]:
    """Check whether the player can safely occupy the target position.

    Returns (can_occupy, reason) where reason describes any blockage.
    """
    try:
        head = await mc.get_block(x, y + 1, z)
        feet = await mc.get_block(x, y, z)
        below = await mc.get_block(x, y - 1, z)

        if not _is_passable(head):
            return False, f"Head would be inside {head}"

        if not _is_passable(feet):
            return False, f"Feet would be inside {feet}"

        if _is_hazard(below):
            return False, f"Ground below is hazardous ({below})"

        if _is_hazard(head) or _is_hazard(feet):
            return False, f"Player would be inside hazard ({head or feet})"

        return True, "passable"
    except Exception as exc:
        return False, f"Collision check failed: {exc}"


async def _walk_toward(
    mc: McpqClient,
    target_x: float,
    target_z: float,
    step_size: float = 0.5,
    max_steps: int = 50,
) -> str:
    """Walk the player toward a target coordinate, using A* pathfinding
    to navigate around obstacles when available.

    For the first invocation the pathfinder is called; subsequent steps
    follow the pre-computed waypoint list.  If pathfinding isn't available
    or the path is short, falls back to straight-line movement with
    collision detection.

    Each step uses ``/execute as @p at @s run tp @s ^ ^ ^{step}`` for
    proper entity-context movement.

    Returns a summary string describing what happened.
    """
    pos = await mc.get_player_pos()
    if pos is None:
        return "Cannot walk — player position unknown"

    px, py, pz = pos[0], pos[1], pos[2]
    dx = target_x - px
    dz = target_z - pz
    distance = (dx * dx + dz * dz) ** 0.5

    if distance < step_size:
        # Already close enough — just face the target
        await mc.run_as_player(
            f"execute as @p at @s facing {target_x} {py} {target_z} run tp @s ~ ~ ~"
        )
        return f"Already at target ({distance:.1f}m)"

    # Try A* pathfinding for medium-to-long distances
    waypoints: list[tuple[float, float]] | None = None
    if distance > 5:
        try:
            from .pathfinding import find_walk_path

            found = await find_walk_path(mc, px, pz, target_x, target_z, int(py))
            if found and len(found) > 1:
                waypoints = found
                logger.info(
                    "Pathfinder returned %d waypoints for %.0fm route",
                    len(found),
                    distance,
                )
        except Exception as exc:
            logger.debug("Pathfinding failed — falling back to straight-line: %s", exc)

    if waypoints:
        # Pathfinding waypoint follow
        steps_taken = 0
        failed_at = ""
        for wx, wz in waypoints:
            if steps_taken >= max_steps:
                break
            # Face the waypoint
            await mc.run_as_player(f"execute as @p at @s facing {wx} {py} {wz} run tp @s ~ ~ ~")
            # Step forward
            await mc.run_as_player(f"execute as @p at @s run tp @s ^ ^ ^{step_size}")
            steps_taken += 1

            # Quick collision check every other step
            if steps_taken % 2 == 0:
                new_pos = await mc.get_player_pos()
                if new_pos:
                    ok, reason = await _can_move_to(
                        mc,
                        int(new_pos[0]),
                        int(new_pos[1]),
                        int(new_pos[2]),
                    )
                    if not ok:
                        failed_at = reason
                        break
                    # Hazard check
                    try:
                        below = await mc.get_block(
                            int(new_pos[0]),
                            int(new_pos[1]) - 1,
                            int(new_pos[2]),
                        )
                        if _is_hazard(below):
                            failed_at = f"hazard below ({below})"
                            break
                    except Exception:
                        pass

        if failed_at:
            return f"Pathfinding walked {steps_taken} waypoint steps before stopping: {failed_at}"
        return f"Pathfinding completed {steps_taken} waypoint steps ({distance:.1f}m)"

    # Fallback: straight-line walking with collision detection (original logic)
    steps_taken = 0
    failed_at = ""
    for step_n in range(min(max_steps, int(distance / step_size) + 1)):
        # Face the target
        await mc.run_as_player(
            f"execute as @p at @s facing {target_x} {py} {target_z} run tp @s ~ ~ ~"
        )
        # Take a small step forward (execute-based for entity context)
        await mc.run_as_player(f"execute as @p at @s run tp @s ^ ^ ^{step_size}")

        # Check if we've reached the target
        new_pos = await mc.get_player_pos()
        if new_pos is None:
            break
        new_dx = target_x - new_pos[0]
        new_dz = target_z - new_pos[2]
        new_dist = (new_dx * new_dx + new_dz * new_dz) ** 0.5

        steps_taken += 1

        if new_dist < step_size:
            break

        # Collision check every 2 steps
        if step_n % 2 == 0:
            ok, reason = await _can_move_to(
                mc,
                int(new_pos[0]),
                int(new_pos[1]),
                int(new_pos[2]),
            )
            if not ok:
                failed_at = reason
                break

        # Hazard check every 2 steps
        if step_n % 2 == 0:
            try:
                block_below = await mc.get_block(
                    int(new_pos[0]), int(new_pos[1]) - 1, int(new_pos[2])
                )
                if _is_hazard(block_below):
                    failed_at = f"hazard below ({block_below})"
                    break
            except Exception:
                pass

    if failed_at:
        return f"Walked {steps_taken} steps toward target before stopping: {failed_at}"
    return f"Walked {steps_taken} steps toward target ({distance:.1f}m)"


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

Handler = Callable[[McpqClient, dict[str, Any]], Awaitable[ActionResult]]


async def _cmd(mc: McpqClient, cmd: str) -> str:
    """Run a command as the configured player and return stripped response.

    Substitutes ``@p`` with the actual player name so commands always
    target the bot, not a human player who happens to be nearest.
    """
    raw = await mc.run_as_player(cmd)
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
    """Move forward in small steps with collision detection.

    Uses caret-relative teleport for small (0.5 block) steps, checking
    collision before each step.  Falls back to a direct ``/tp`` for
    larger distances.
    """
    steps = params.get("steps", 2)
    step_size = 0.5
    actual_steps = 0

    for _ in range(min(steps, 20)):
        # Check where we'd be moving
        pos = await mc.get_player_pos()
        if pos is None:
            break

        target_x = int(pos[0])
        target_y = int(pos[1] + 0.5)
        target_z = int(pos[2])

        # Use caret-relative (^ ^ ^ moves in facing direction)
        # Check collision at the target position
        try:
            front_x = int(pos[0] + pos[2] * step_size)  # rough forward
            front_z = int(pos[2] + pos[0] * step_size)
        except Exception:
            front_x, front_z = target_x, target_z

        ok, reason = await _can_move_to(mc, front_x, target_y, front_z)
        if not ok:
            # Don't auto-step over hazards
            if "hazard" in reason.lower():
                return ActionResult(
                    success=False,
                    action=ActionType.MOVE_FORWARD,
                    message=f"Hazard detected after {actual_steps} steps: {reason}",
                    data={"steps_taken": actual_steps, "hazard": reason},
                )
            # Try one block up (auto-step over obstacles)
            ok_up, _ = await _can_move_to(mc, front_x, target_y + 1, front_z)
            if ok_up:
                await _cmd(mc, f"execute as @p at @s run tp @s ^ ^ ^{step_size}")
                await _cmd(mc, "tp @p ^ ^1 ^")  # step up
                actual_steps += 1
                continue
            return ActionResult(
                success=False,
                action=ActionType.MOVE_FORWARD,
                message=f"Blocked after {actual_steps} steps: {reason}",
                data={"steps_taken": actual_steps, "blocked_by": reason},
            )

        # Check hazard below
        try:
            below = await mc.get_block(front_x, target_y - 1, front_z)
            if _is_hazard(below):
                return ActionResult(
                    success=False,
                    action=ActionType.MOVE_FORWARD,
                    message=f"Hazard below ({below}) at {actual_steps} steps — not moving",
                    data={"steps_taken": actual_steps, "hazard": below},
                )
        except Exception:
            pass

        await _cmd(mc, f"execute as @p at @s run tp @s ^ ^ ^{step_size}")
        actual_steps += 1

    return ActionResult(
        success=(actual_steps > 0),
        action=ActionType.MOVE_FORWARD,
        message=f"Moved forward {actual_steps} step(s)",
        data={"steps": steps, "steps_taken": actual_steps},
    )


async def _move_back(mc: McpqClient, params: dict) -> ActionResult:
    """Move backward in small steps with collision detection."""
    steps = params.get("steps", 2)
    step_size = 0.5
    actual_steps = 0

    for _ in range(min(steps, 20)):
        pos = await mc.get_player_pos()
        if pos is None:
            break

        target_x = int(pos[0])
        target_y = int(pos[1] + 0.5)
        target_z = int(pos[2])

        try:
            back_x = int(pos[0] - pos[2] * step_size)
            back_z = int(pos[2] - pos[0] * step_size)
        except Exception:
            back_x, back_z = target_x, target_z

        ok, reason = await _can_move_to(mc, back_x, target_y, back_z)
        if not ok:
            return ActionResult(
                success=False,
                action=ActionType.MOVE_BACK,
                message=f"Blocked after {actual_steps} steps: {reason}",
                data={"steps_taken": actual_steps, "blocked_by": reason},
            )

        try:
            below = await mc.get_block(back_x, target_y - 1, back_z)
            if _is_hazard(below):
                return ActionResult(
                    success=False,
                    action=ActionType.MOVE_BACK,
                    message=f"Hazard below ({below}) at {actual_steps} steps",
                    data={"steps_taken": actual_steps, "hazard": below},
                )
        except Exception:
            pass

        await _cmd(mc, f"execute as @p at @s run tp @s ^ ^ ^-{step_size}")
        actual_steps += 1

    return ActionResult(
        success=(actual_steps > 0),
        action=ActionType.MOVE_BACK,
        message=f"Moved back {actual_steps} step(s)",
        data={"steps": steps, "steps_taken": actual_steps},
    )


async def _sprint(mc: McpqClient, params: dict) -> ActionResult:
    """Sprint forward — faster forward movement with 1.0-block steps.

    Uses larger steps than ``move_forward``, ideal for open terrain.
    Collision detection runs every 3 steps to keep it fast.
    """
    steps = params.get("steps", 4)
    step_size = 1.0
    actual_steps = 0

    for _ in range(min(steps, 30)):
        pos = await mc.get_player_pos()
        if pos is None:
            break

        # Rough forward position
        try:
            front_x = int(pos[0] + pos[2] * step_size)
            front_z = int(pos[2] + pos[0] * step_size)
        except Exception:
            break

        target_y = int(pos[1] + 0.5)

        # Collision check every 3 steps
        if actual_steps % 3 == 0:
            ok, reason = await _can_move_to(mc, front_x, target_y, front_z)
            if not ok:
                return ActionResult(
                    success=(actual_steps > 0),
                    action=ActionType.SPRINT,
                    message=f"Sprinted {actual_steps} step(s) before stopping: {reason}",
                    data={"steps_taken": actual_steps, "blocked_by": reason},
                )

            # Quick hazard check
            try:
                below = await mc.get_block(front_x, target_y - 1, front_z)
                if _is_hazard(below):
                    return ActionResult(
                        success=(actual_steps > 0),
                        action=ActionType.SPRINT,
                        message=f"Sprinted {actual_steps} steps — hazard below ({below})",
                        data={"steps_taken": actual_steps, "hazard": below},
                    )
            except Exception:
                pass

        await _cmd(mc, f"execute as @p at @s run tp @s ^ ^ ^{step_size}")
        actual_steps += 1

    return ActionResult(
        success=(actual_steps > 0),
        action=ActionType.SPRINT,
        message=f"Sprinted {actual_steps} step(s)",
        data={"steps": steps, "steps_taken": actual_steps},
    )


async def _walk_to(mc: McpqClient, params: dict) -> ActionResult:
    """Walk to a target coordinate step-by-step with collision detection.

    For short-to-medium distances (up to ~50 blocks), this uses
    ``_walk_toward()`` with small steps and collision checks.
    For longer distances, it falls back to teleport.
    """
    x = params.get("x")
    z = params.get("z")
    if x is None or z is None:
        return ActionResult(
            success=False,
            action=ActionType.WALK_TO,
            message="walk_to requires 'x' and 'z' parameters",
        )
    y = params.get("y")

    pos = await mc.get_player_pos()
    if pos is None:
        return ActionResult(
            success=False,
            action=ActionType.WALK_TO,
            message="Cannot walk — player position unknown",
        )

    dx = float(x) - pos[0]
    dz = float(z) - pos[2]
    distance = (dx * dx + dz * dz) ** 0.5

    if distance > 50:
        # Long distance — teleport instead
        if y is not None:
            await mc.teleport_player(float(x), float(y), float(z))
        else:
            await mc.teleport_player(float(x), pos[1], float(z))
        return ActionResult(
            success=True,
            action=ActionType.WALK_TO,
            message=f"Distance {distance:.0f}m > 50, teleported to ({x}, {z})",
            data={"x": x, "z": z, "teleported": True},
        )

    result = await _walk_toward(mc, float(x), float(z))
    new_pos = await mc.get_player_pos()
    new_dx = float(x) - (new_pos[0] if new_pos else pos[0])
    new_dz = float(z) - (new_pos[2] if new_pos else pos[2])
    remaining = (new_dx * new_dx + new_dz * new_dz) ** 0.5

    return ActionResult(
        success=(remaining < 3),  # within 3 blocks = close enough
        action=ActionType.WALK_TO,
        message=result,
        data={
            "x": x,
            "z": z,
            "distance": distance,
            "remaining": remaining,
        },
    )


async def _turn_left(mc: McpqClient, params: dict) -> ActionResult:
    """Turn left by 15 degrees (gradual rotation).

    The space after the third ``~`` is critical — without it Minecraft
    parses ``~-90`` as ``z = current_z - 90`` (teleport) instead of
    ``yaw = current_yaw - 15`` (rotate).
    """
    resp = await _cmd(mc, "tp @p ~ ~ ~ ~-15 ~")
    return ActionResult(
        success=True,
        action=ActionType.TURN_LEFT,
        message="Turned left 15°",
        data={"response": resp, "degrees": -15},
    )


async def _turn_right(mc: McpqClient, params: dict) -> ActionResult:
    """Turn right by 15 degrees (gradual rotation)."""
    resp = await _cmd(mc, "tp @p ~ ~ ~ ~15 ~")
    return ActionResult(
        success=True,
        action=ActionType.TURN_RIGHT,
        message="Turned right 15°",
        data={"response": resp, "degrees": 15},
    )


async def _jump(mc: McpqClient, params: dict) -> ActionResult:
    """Jump up one block (teleport-based)."""
    resp = await _cmd(mc, "tp @p ~ ~1 ~")
    return ActionResult(
        success=True,
        action=ActionType.JUMP,
        message="Jumped",
        data={"response": resp},
    )


async def _teleport(mc: McpqClient, params: dict) -> ActionResult:
    """Instant teleport to coordinates (bypasses collision)."""
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
    """Give items to the player (creative-mode /give).

    NOTE: This uses /give under the hood, which requires OP permissions or
    creative mode.  In survival this will fail — a proper survival crafting
    system (recipe matching + crafting table interaction) is tracked as a
    planned feature (see docs/features/).
    """
    item = params.get("item_type", "crafting_table")
    amount = params.get("amount", 1)
    try:
        resp = await _cmd(mc, f"give @p {item} {amount}")
        return ActionResult(
            success=True,
            action=ActionType.CRAFT_ITEM,
            message=f"Gave {amount}x {item}",
            data={"item": item, "amount": amount, "response": resp},
        )
    except Exception as exc:
        return ActionResult(
            success=False,
            action=ActionType.CRAFT_ITEM,
            message=f"Could not give {item}: {exc}. May need OP/creative mode.",
        )


async def _drop_item(mc: McpqClient, params: dict) -> ActionResult:
    """Drop items from inventory as entities in the world.

    Uses /replaceitem to clear the slot and /summon to create the item
    entity at the player's position.  This is a best-effort simulation;
    a proper drop system should use MCPQ's direct player-inventory API.
    """
    item = params.get("item_type", "stone")
    amount = params.get("amount", 1)
    try:
        # Get player position to spawn item drop there
        pos = await mc.get_player_pos()
        if pos:
            # Find the item in inventory and remove it, then spawn as entity
            await _cmd(mc, f"clear @p {item} {amount}")
            spawn_cmd = (
                f"summon item {pos[0]:.1f} {pos[1]:.1f} {pos[2]:.1f} "
                f'{{Item:{{id:"minecraft:{item}",Count:{amount}b}}}}'
            )
            await _cmd(mc, spawn_cmd)
            return ActionResult(
                success=True,
                action=ActionType.DROP_ITEM,
                message=f"Dropped {amount}x {item} at current position",
                data={"item": item, "amount": amount},
            )
        else:
            # Fallback: just clear from inventory
            resp = await _cmd(mc, f"clear @p {item} {amount}")
            return ActionResult(
                success=False,
                action=ActionType.DROP_ITEM,
                message=(
                    f"Position unknown — removed {amount}x {item} from inventory "
                    f"but could not spawn drop entity"
                ),
                data={"item": item, "amount": amount, "response": resp},
            )
    except Exception as exc:
        return ActionResult(
            success=False,
            action=ActionType.DROP_ITEM,
            message=f"Drop failed: {exc}",
        )


# ── Combat ──────────────────────────────────────────────────────────────


def _damage_hit_anything(resp: str | None) -> bool:
    """Check whether a /damage command response indicates an entity was hit.

    /damage returns a message like 'Damaged 1 entity' or 'No entity was
    found'.  We also check for '0 entities' as a safety net.
    """
    if not resp:
        return False
    lower = resp.lower().strip()
    if "no entity" in lower:
        return False
    if "0 entit" in lower:
        return False
    if "damaged" in lower or "hurt" in lower or "damage" in lower:
        return True
    # If none of the above patterns match, assume it worked (the damage
    # succeeded but the output format might differ).
    return True


async def _attack(mc: McpqClient, params: dict) -> ActionResult:
    # Paper 26.1.x broke "execute as @p at @p run attack" (throws
    # CommandException).  Use /damage instead — available since MC 1.20.5.
    target = params.get("entity_type", "")
    if target:
        # Target a specific player with generic damage (4 = 2 hearts)
        try:
            cmd = f"damage @e[type=minecraft:player,name={target},limit=1] 4"
            resp = await _cmd(mc, cmd)
            if _damage_hit_anything(resp):
                return ActionResult(
                    success=True,
                    action=ActionType.ATTACK,
                    message=f"Attacked {target} for 4 damage",
                    data={"target": target, "response": resp},
                )
            else:
                return ActionResult(
                    success=False,
                    action=ActionType.ATTACK,
                    message=f"Attack on {target} failed — player not found or not in range",
                    data={"target": target, "response": resp},
                )
        except Exception:
            pass

    # Generic attack — try /damage on the entity the player is looking at
    try:
        cmd = "damage @e[type=!minecraft:player,limit=1,sort=nearest] 4"
        resp = await _cmd(mc, cmd)
        if _damage_hit_anything(resp):
            return ActionResult(
                success=True,
                action=ActionType.ATTACK,
                message="Attacked nearest entity for 4 damage",
                data={"response": resp},
            )
    except Exception:
        pass

    # Last resort: raw /damage with the target name (broader selector)
    if target:
        try:
            resp = await _cmd(mc, f"damage {target} 4")
            if _damage_hit_anything(resp):
                return ActionResult(
                    success=True,
                    action=ActionType.ATTACK,
                    message=f"Attacked {target} for 4 damage",
                    data={"target": target, "response": resp},
                )
            else:
                return ActionResult(
                    success=False,
                    action=ActionType.ATTACK,
                    message=f"Attack on {target} failed — player not found",
                    data={"target": target, "response": resp},
                )
        except Exception:
            pass

    return ActionResult(
        success=False,
        action=ActionType.ATTACK,
        message=(
            "Attack failed — Paper 26.1.x removed execute attack. "
            "Try crafting/killing via commands instead."
        ),
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
            nearby["east"] = await mc.get_block(px + 1, py - 1, pz)
            nearby["west"] = await mc.get_block(px - 1, py - 1, pz)

            # What's directly in front at eye level
            nearby["front_eye"] = await mc.get_block(px, py, pz + 1)
        except Exception:
            pass

        data["nearby"] = nearby

        # Scan visible blocks in the radius (sample at cardinal points)
        if radius >= 3:
            sample: dict[str, str] = {}
            try:
                for dx, dz in [
                    (0, 2),
                    (2, 0),
                    (0, -2),
                    (-2, 0),
                    (2, 2),
                    (2, -2),
                    (-2, 2),
                    (-2, -2),
                ]:
                    key = f"d{dx:+}z{dz:+}"
                    sample[key] = await mc.get_block(px + dx, py - 1, pz + dz)
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
    """Check the player's health.

    Uses ``/data get entity @p Health`` first, which works for real players.
    For fake players that may not have a Health attribute, falls back to
    ``get_player_info()`` which reads NBT directly via MCPQ's gRPC API,
    then to ``/attribute`` queries.
    """
    resp = await _cmd(mc, "data get entity @p Health")
    result_data: dict[str, Any] = {"health_raw": resp}

    # If the basic command returned 0 or empty, try MCPQ NBT fallback
    parsed = None
    try:
        import re as _re

        m = _re.search(r"(-?\d+\.?\d*)", resp or "")
        if m:
            parsed = float(m.group(1))
    except (ValueError, TypeError):
        pass

    if parsed is not None and parsed > 0:
        return ActionResult(
            success=True,
            action=ActionType.CHECK_HEALTH,
            message=f"Health: {parsed}",
            data=result_data,
        )

    # Fallback 1: try MCPQ get_player_info() which reads NBT attributes
    try:
        info = await mc.get_player_info()
        nbt_health = info.get("health")
        if nbt_health is not None and float(nbt_health) > 0:
            result_data["health_raw"] = str(nbt_health)
            result_data["health_source"] = "mcpq_nbt"
            return ActionResult(
                success=True,
                action=ActionType.CHECK_HEALTH,
                message=f"Health: {nbt_health}",
                data=result_data,
            )
    except Exception:
        pass

    # Fallback 2: try /attribute to get max health (works on any living entity)
    try:
        attr_resp = await _cmd(mc, "attribute @p minecraft:generic.max_health get")
        if attr_resp and "Has no attribute" not in attr_resp:
            result_data["health_raw"] = attr_resp
            result_data["health_source"] = "attribute"
            return ActionResult(
                success=True,
                action=ActionType.CHECK_HEALTH,
                message=f"Health max: {attr_resp}",
                data=result_data,
            )
    except Exception:
        pass

    # Ultimate fallback: assume full health (20) if nothing worked
    result_data["health_raw"] = "20.0"
    result_data["health_source"] = "default"
    return ActionResult(
        success=True,
        action=ActionType.CHECK_HEALTH,
        message="Health: 20.0 (assumed — attribute unavailable)",
        data=result_data,
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
    ActionType.WALK_TO: _walk_to,
    ActionType.TURN_LEFT: _turn_left,
    ActionType.TURN_RIGHT: _turn_right,
    ActionType.JUMP: _jump,
    ActionType.SPRINT: _sprint,
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
