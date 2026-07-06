# WASD-Style Human-Like Movement

**Status:** ✅ **Implemented** (v0.5.0)
**Priority:** High
**Dependencies:** Scanner, coordinate awareness, MCPQ execute-command

## Summary

WASD-style movement has been implemented. Movement now uses `/execute`-based entity
movement with collision detection, hazard avoidance, and auto-step-over for obstacles.
The agent can walk step-by-step to targets using `walk_to`, and all movement actions
(`move_forward`, `move_back`, `turn_left`, `turn_right`, `jump`) use physics-based
stepping instead of raw `/tp` teleport.

### What Changed
- `walk_to` action uses `_walk_toward()` — step-by-step `/execute facing` + `/tp ^ ^ ^0.5`
- `move_forward`/`move_back` check collision before each step, auto-step up for obstacles
- `turn_left`/`turn_right` use 15° gradual rotation (not 90°)
- Collision detection (`_can_move_to()`) checks head/feet/hazard blocks
- `_is_passable()`, `_is_hazard()`, `_is_artificial()` helpers for block classification
- The system prompt recommends `walk_to` for short-to-medium distances, `move_to`/`teleport` for long-range

### Known Limitations
- Still uses `/tp` commands under the hood (via `/execute`), not raw WASD input simulation
- No fall damage or hunger cost (works in creative mode)
- Pathfinding is greedy (step toward target) — no A* for complex terrain yet
- Movement in survival mode needs further testing

Replace the instant-teleport movement (`/tp @p`) with step-by-step human-like movement using `/execute`-based entity commands, enabling survival-mode compatibility and natural interaction with the world.

## Implementation

### Collision Detection

Before each movement step, the target block is scanned:

```python
async def _can_move_to(mc, x, y, z):
    head = await mc.get_block(x, y + 1, z)
    feet = await mc.get_block(x, y, z)
    below = await mc.get_block(x, y - 1, z)
    # Must be passable at head + feet, no hazards
    return _is_passable(head) and _is_passable(feet) and not _is_hazard(below) and not _is_hazard(head) and not _is_hazard(feet)
```

### Execute-Based Movement Commands

All movement now uses `/execute as @p at @s run` patterns:

| Action | Command | Notes |
|--------|---------|-------|
| `move_forward` | `execute as @p at @s run tp @s ^ ^ ^0.5` | 0.5-block caret-relative steps |
| `move_back` | `execute as @p at @s run tp @s ^ ^ ^-0.5` | Backward steps |
| `turn_left` | `execute as @p at @s run tp @s ~ ~ ~ ~-15 ~` | 15° left rotation |
| `turn_right` | `execute as @p at @s run tp @s ~ ~ ~ ~15 ~` | 15° right rotation |
| `jump` | `execute as @p at @s run tp @s ~ ~1 ~` | One-block jump |
| `walk_to` | Step-by-step via `_walk_toward()` | Uses `/execute facing` + caret teleport |
| `teleport` / `move_to` | `tp @p <x> <y> <z>` | Fallback for long distances |

### Auto-Step-Over

When a collision is detected at the target position, the system automatically tries one block up (for slabs, stairs, carpets):

1. Check if `_can_move_to(x, y+1, z)` is passable
2. If yes: move forward 0.5 blocks, then step up 1 block
3. If no: report obstruction and stop

### Hazard Avoidance

Before each step:
- Check the block below the target for hazards (lava, fire, cactus, magma)
- Check the feet/head positions for hazards
- If a hazard is detected, the step is aborted with a descriptive error

### Walking to Coordinates

The `walk_to` action (recommended for all short-to-medium distance movement):
- If distance > 50 blocks → falls back to teleport
- If distance <= 50 blocks → uses `_walk_toward()` with step-by-step collision-checked walking
- Returns success if within 3 blocks of the target

## What Changed

1. **`actions.py`**: All movement handlers (`_move_forward`, `_move_back`, `_turn_left`, `_turn_right`, `_jump`) replaced bare `/tp` commands with `/execute as @p at @s run tp @s` patterns. Added auto-jump for obstacles, collision checks before every step, and hazard detection.

2. **`prompts.py`**: SYSTEM_PROMPT updated to recommend `walk_to` as the default movement action for short-to-medium distances.

3. **`tests/test_actions.py`**: Added tests verifying:
   - Commands use `/execute as @p at @s run` pattern
   - Step-by-step movement with collision detection
   - Auto-jump over obstacles
   - Hazard avoidance (stops before lava)
   - Backward movement with execute-based commands

## Remaining Work (Future)

- A*-based pathfinding for multi-block navigation
- Hunger-aware movement (slow down when food is low)
- Sprint toggle
- Sneak mode for edge-walking
- Elytra flight detection + glide control
- Full survival-mode physics (fall damage, hunger cost)
