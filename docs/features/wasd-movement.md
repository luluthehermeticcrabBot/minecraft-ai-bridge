# WASD-Style Human-Like Movement

**Status:** Planning  
**Priority:** High  
**Dependencies:** Scanner, coordinate awareness, MCPQ execute-command  

## Goal

Replace the current instant-teleport movement (`/tp @p`) with
step-by-step human-like movement using WASD controls, enabling
survival-mode compatibility and natural interaction with the world.

## Current Implementation

All movement currently uses Minecraft's `/tp` command:
- `move_forward`: `tp @p ^ ^ ^{steps}` (relative forward via caret notation)
- `move_back`: `tp @p ^ ^ ^-{steps}`
- `turn_left`: `tp @p ~ ~ ~ ~-90 ~`
- `turn_right`: `tp @p ~ ~ ~ ~90 ~`
- `jump`: `tp @p ~ ~1 ~`
- `teleport` / `move_to`: `tp @p <x> <y> <z>`

This works in creative mode but has several limitations:
- Ignores collision detection (walks through walls)
- No fall damage
- No hunger cost
- Can teleport through blocks
- Doesn't trigger pressure plates, tripwires, etc.

## Planned Architecture

### Level 1: Execute-Based Movement (NEXT)

Replace `/tp` with `/execute`-based movement that simulates WASD input:

```
move_forward  → execute as @p at @s run tp @s ^ ^ ^0.5
turn_left     → execute as @p at @s run tp @s ~ ~ ~ ~-15 ~
```

Key differences:
- Small incremental steps (0.5 blocks instead of multi-block teleports)
- Gradual rotation (15° instead of 90°)
- Actual entity movement (triggers collisions, fall, etc.)

### Level 2: Collision Detection

Before each movement step, scan the target block:
- If the block is solid, don't move there (avoid walking through walls)
- If the block is a drop-off, check if the fall is survivable
- Auto-jump over single-block obstacles (slabs, carpets)

```python
async def _can_move_to(self, x: int, y: int, z: int) -> bool:
    """Check if the player can occupy this space."""
    # Must be air or passable block at head level
    head = await mc.get_block(x, y + 1, z)
    # Must be air or passable at feet level  
    feet = await mc.get_block(x, y, z)
    # Ground below
    below = await mc.get_block(x, y - 1, z)
    return (
        _is_passable(head) and
        _is_passable(feet) and
        not _is_hazard(below)  # e.g. lava, cactus
    )
```

### Level 3: Pathfinding

Replace simple directional movement with A*-based pathfinding:
- Target coordinate → BFS/A* through walkable blocks
- Respect Y-level changes (stairs, slabs, ladders)
- Avoid hazards (lava, cactus, cliffs)

Implementation options:
- **MCPQ + local search**: Scan blocks around the player, build a local
  graph, route through it. Cheap enough for a single step per turn.
- **Pre-computed map**: Not feasible without a full world download (too
  large for typical servers).

### Level 4: Survival Enhancements

- Hunger-aware movement: slow down when food is low
- F3-debug-style info overlay for the LLM (speed, direction, biome)
- Sprint toggle for faster travel
- Sneak mode for edge-walking
- Elytra flight detection + glide control

## Comparison With Other Bot Projects

| Project | Movement | Collision | Survival |
|---------|----------|-----------|----------|
| **Mineflayer (JS)** | Full WASD via node-minecraft-protocol | Yes | Yes |
| **pyCraft (Python)** | Packet-level player movement | Partial | Yes (outdated) |
| **Baritone (Java)** | Full pathfinding (A*) | Yes | Yes |
| **MCPQ Bot (this project)** | `/tp` teleport | No | No |

The goal is to reach Mineflayer-level movement fidelity while staying
within the MCPQ plugin architecture (no client-side mod needed).

## Implementation Plan

1. Add `_walk_to(x, y, z)` method to `McpqClient` — uses `/execute`
   with small steps + collision checks
2. Replace `_move_to` handler in `actions.py` to use `_walk_to` when
   in survival mode, fall back to `/tp` in creative
3. Add `_is_passable()` and `_is_hazard()` helpers
4. Add pathfinding for multi-block navigation
5. Add `collision` field to `WorldState` (nearby solid blocks)
6. Update action descriptions and SYSTEM_PROMPT for the new movement
