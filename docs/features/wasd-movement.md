# WASD-Style Human-Like Movement

**Status:** Implemented (Levels 1-3), Planning (Level 4)
**Priority:** High
**Dependencies:** Scanner, coordinate awareness, MCPQ execute-command

## Goal

Replace the current instant-teleport movement (`/tp @p`) with
step-by-step human-like movement using WASD controls, enabling
survival-mode compatibility and natural interaction with the world.

## Current Implementation (v0.5.0+)

All movement now uses **execute-based entity movement** (`/execute as @p at @s run tp @s ^ ^ ^`)
instead of raw `/tp @p` commands, giving proper entity context for collisions.

| Action | Implementation | Notes |
|--------|---------------|-------|
| `move_forward` | 0.5-block steps via execute, collision-checked, auto-steps up over 1-block obstacles | ✅ Fully implemented |
| `move_back` | Same backwards with collision detection | ✅ Fully implemented |
| `sprint` | 1.0-block steps via execute, collision-checked every 3 steps, faster travel | ✅ New (v0.5.0) |
| `turn_left` / `turn_right` | 15° gradual rotation via `/tp ~ ~ ~ ~-15 ~` | ✅ Fully implemented |
| `walk_to` | A*-pathfinding waypoint following + straight-line fallback | ✅ Upgraded (v0.5.0) |
| `_can_move_to()` | Collision detection (head + feet + below + hazard) | ✅ Fully implemented |
| `_walk_toward()` | Shared helper used by walk_to, move_forward, move_back | ✅ Fully implemented |
| **Pathfinder** | A* on 2D walkability grid scanned via MCPQ `getBlock` | ✅ New (v0.5.0) |

### Level 1: Execute-Based Movement ✅

All movement commands use:
```
execute as @p at @s run tp @s ^ ^ ^{0.5}
```
instead of the old `tp @p ^ ^ ^{0.5}`. This runs the teleport in the
entity's coordinate context, enabling proper collision, fall damage,
and pressure-plate/trigger interactions.

### Level 2: Collision Detection ✅

Before each movement step, `_can_move_to()` checks:
- Head block is passable (no suffocation)
- Feet block is passable (no walking into walls)
- Block below is not a hazard (lava, fire, cactus)
- Auto-step up over 1-block obstacles (slabs, carpets, small walls)

### Level 3: A* Pathfinding ✅ (v0.5.0)

`walk_to` now uses a new `Pathfinder` module that:
1. Scans a walkability grid around the player-to-goal corridor via MCPQ
2. Runs A* with 8-directional movement (cardinal + diagonal)
3. Returns waypoints for the agent to follow step-by-step
4. Falls back to straight-line movement if pathfinding fails or distance is small

The pathfinder handles:
- Walls (goes around them)
- Hazards (lava, fire — routes away)
- Large areas (up to ~500 nodes, clipped to bounding box)
- MCPQ failures (fails gracefully to straight-line fallback)

### Level 4: Survival Enhancements (PLANNED)

- [ ] Hunger-aware movement: slow down when food is low
- [ ] F3-debug-style info overlay for the LLM (speed, direction, biome)
- [ ] Sprint toggle for faster travel (✅ done — sprint action)
- [ ] Sneak mode for edge-walking
- [ ] Elytra flight detection + glide control

## Architecture

```python
# Pathfinding integration in _walk_toward():
if distance > 5:
    waypoints = await find_walk_path(mc, px, pz, tx, tz, int(py))
    if waypoints:
        for wx, wz in waypoints:
            face_waypoint(mc, wx, wz)
            take_step(mc)
else:
    # Straight-line with collision detection (original logic)
    ...
```

## Comparison With Other Bot Projects

| Project | Movement | Collision | Pathfinding | Survival |
|---------|----------|-----------|-------------|----------|
| **Mineflayer (JS)** | Full WASD via node-minecraft-protocol | Yes | Yes | Yes |
| **pyCraft (Python)** | Packet-level player movement | Partial | No | Yes (outdated) |
| **Baritone (Java)** | Full pathfinding (A*) | Yes | Yes | Yes |
| **MCPQ Bot (this project)** | Execute-based movement | Yes | Yes (A*) | No |

The goal is to reach Mineflayer-level movement fidelity while staying
within the MCPQ plugin architecture (no client-side mod needed).

## Implementation Details

### Pathfinder Module (`minecraft_ai_bridge/minecraft/pathfinding.py`)

- `Pathfinder` class with `find_path(start_x, start_z, goal_x, goal_z, y_level)`
- Scans bounding box around start→goal corridor
- A* with Chebyshev heuristic for 8-directional movement
- Blocks fetched in concurrent batches (25 per batch) for performance
- Max 500 nodes explored, auto-clips large areas
- `find_walk_path()` convenience wrapper

### Movement Commands

- `move_forward(mc, {"steps": 2})` — small steps with full collision
- `sprint(mc, {"steps": 4})` — 1-block steps, collision every 3 steps
- `walk_to(mc, {"x": 10, "z": 20})` — A* pathfinding to coordinate
- For distances > 50 blocks, `walk_to` still teleports (practical limit)

## References

- `minecraft_ai_bridge/minecraft/pathfinding.py` — A* pathfinder
- `minecraft_ai_bridge/minecraft/actions.py` — `_walk_toward`, `_sprint`, `_can_move_to`, `_is_passable`, `_is_hazard`
- `tests/test_pathfinding.py` — 10 tests for pathfinder
- `tests/test_actions.py` — 4 tests for sprint
