# Agent Diary — Features, Movement Planning & Skill Exploration

**Date:** 2026-05-13  
**Agent:** OpenCode Orchestrator  
**Model:** big-pickle  

## Summary

Completed Phases 4-6: persistent memory (N3), chat commands (N4), inventory manager (N1), WASD movement planning, survival mode planning with YOLO threat detection, structure respect rules, and OpenCode/Hermes Agent sidecar exploration.

## Phase 4: New Features Implemented

### N3 — Persistent Memory Database (`bridge/memory.py`)

SQLite-backed persistence for the agent's long-term facts:

- **Two tables**: `agent_facts` (unique facts with timestamps) and `agent_goals` (goal descriptions with completion status + session IDs)
- **WAL mode** with `synchronous=NORMAL` for concurrent-read performance
- **Thread-local connections** via `threading.local()` — each thread gets its own connection, avoiding sqlite3 thread-safety issues
- **Load on init**: Facts from previous sessions are restored on startup
- **Save on remember**: Each `remember_fact()` call persists to DB immediately
- **Close**: `close()` method triggers WAL checkpoint + connection close, called during orchestrator `_disconnect()`
- **Fallback**: If DB init fails (permissions, missing directory), gracefully falls back to in-memory only
- **Config**: DB path via `AGENT_MEMORY_DB` env var or `db_path` parameter (default: in-memory)

**Design decision**: Short-term (turn-by-turn) memory stays in-memory. Only long-term facts survive restarts. Persisting all turns would create unbounded DB growth and isn't useful — the LLM only sees the last ~15 entries anyway.

### N4 — Chat Command Interface (`bridge/chat_commands.py`)

In-game chat commands for human-in-the-loop control:

| Command | Action | Implementation |
|---------|--------|----------------|
| `!status` | Report goal, turn count, position | Reads `_goals.current_goal`, `_turn`, calls `mc.get_player_pos()` |
| `!stop` | Graceful shutdown | Sets `_stop_requested = True` (checked in main loop next iteration) |
| `!goal <desc>` | Re-assign goal mid-session | Clears short-term memory, calls `_goals.set_goal(new_desc)` |
| `!goto <player>` | Teleport to named player | `tp @p <player>` via MCPQ command |
| `!follow <player>` | Follow a player (toggle) | Sets `_follow_target`, each turn does `execute as <target> run tp @p` |
| `!come` | Teleport speaker to agent | `tp <sender> @p` |
| `!help` | List available commands | Static help text |

**Polling mechanism**: The chat command parser uses a regex (`<PlayerName> !command args`) to detect in-game chat messages. Currently uses a best-effort poll since MCPQ's chat listener API is limited. The `_last_check` dedup ensures each batch is only processed once.

**Follow mode**: When `!follow` is active, the orchestrator's `_step()` method teleports the agent to the target player every turn. This is a simple `/execute ... run tp` — adequate for creative mode.

**Design decision**: Commands run in the same async context as the agent loop. No separate thread needed. The polling adds negligible overhead (one MCPQ call per turn).

### N1 — Inventory Manager (`bridge/inventory_manager.py`)

Structured inventory query layer on top of the observer's NBT parser:

- `refresh()` — fetches inventory via `check_inventory` action, parses via `_parse_inventory_nbt()`
- `has_item(item_id, min_count=1)` — boolean check
- `count_item(item_id)` — total count across all slots (strips `minecraft:` prefix for comparison)
- `get_item_slots(item_id)` — all slots containing a specific item
- `get_hotbar()` / `get_armor()` / `get_offhand()` — slot-typed queries
- `summary` property — compact human-readable for LLM prompt ("Inventory (3 slots used, 2 types): oak_planksx10, stickx4")
- `total_slots_used()` / `total_item_types()` / `item_count` — aggregate stats

**Integration**: Inventory refreshes every 5 turns in the orchestrator loop (configurable). The `summary` string is available for the LLM prompt.

### System Prompt Updates

Rules 11-13 added to `SYSTEM_PROMPT` in `prompts.py`:

> **Rule 11**: RESPECT EXISTING STRUCTURES — scan before placing blocks, check for artificial blocks (planks, glass, doors, beds, rails, torches on walls, farmland, etc.)
> **Rule 12**: AVOID VILLAGES — don't modify NPC village buildings unless explicitly instructed
> **Rule 13**: PRESERVE INFRASTRUCTURE — railroads, bridges, paths must not be blocked or modified

The `format_state()` function also now includes `biome` in the output (from I4).

## Phase 5: WASD Movement & Survival Mode Planning

### WASD Movement Plan (`docs/features/wasd-movement.md`)

Four-level implementation plan:

| Level | Description | Key Change |
|-------|-------------|------------|
| 1 | Execute-based movement | Replace `/tp` with `/execute ... run tp` with small steps + gradual rotation |
| 2 | Collision detection | Scan target blocks before moving; avoid walls, hazards, falls |
| 3 | Pathfinding | A*/BFS through walkable blocks; respect Y-level changes |
| 4 | Survival enhancements | Hunger-aware speed, sprint, sneak, elytra |

**Comparison with other bot projects:**

| Project | Movement | Collision | Survival |
|---------|----------|-----------|----------|
| **Mineflayer (JS)** | Full WASD | Yes | Yes |
| **pyCraft (Python)** | Packet-level player | Partial | Yes (outdated) |
| **Baritone (Java)** | Full pathfinding (A*) | Yes | Yes |
| **MCPQ Bot (this project)** | `/tp` teleport | No | No |

Goal: reach Mineflayer-level movement fidelity within MCPQ architecture.

### Survival Mode Plan (`docs/features/survival-mode.md`)

Six-phase approach:

- **Phase 1**: WASD movement (prerequisite)
- **Phase 2**: Survival crafting (recipe DB, crafting table, furnace, tool progression)
- **Phase 3**: Hunting & food (passive mobs only, risk assessment matrix)
- **Phase 4**: Self-defense (hostile mob threat assessment, defensive protocol)
- **Phase 5**: YOLO-based fast threat detection (detailed below)
- **Phase 6**: Full survival autonomy (Ender Dragon)

**Risk Assessment Matrix**: When deciding to engage, the agent evaluates:
- Current health (< 10HP → retreat)
- Armor (none → avoid all hostiles)
- Weapon (fist only → avoid armored mobs)
- Mob count (3+ → retreat)
- Time of day (night → more cautious)
- Biome (Nether → defensive, never chase)

**Prohibited Targets**: Villagers, illagers, iron golems, witches, endermen, zombified piglins — too dangerous or strategically counterproductive.

**YOLO Integration** (`docs/features/survival-mode.md` Phase 5):

YOLO solves the latency problem of vision LLMs: 20-50ms on CPU vs 2-5s for GPT-4o/Claude vision. A creeper explodes in 1.5s (30 ticks @ 20tps). Vision LLM alone can't react fast enough.

Architecture recommendation:
- **YOLOv8n** (3.2MB model, 20-30ms CPU, 1-2ms GPU) as primary
- Runs in bridge container via ONNX Runtime
- Background task every ~1 second
- Outputs structured threat report to LLM (not raw pixels)
- Optional/pluggable — bridge works without it

Training data sources: RoboFlow "Minecraft Mob Detection" (3.5k images), Kaggle (~900 images), synthetic renders, self-supervised from own server screenshots.

## Phase 6: OpenCode & Hermes Agent Skill Exploration

### Current Integration

The bridge already supports OpenCode as an LLM provider via `OpenCodeServerClient`:
- `POST /sessions` to create sessions
- `POST /session/{id}/message` for inference
- Extracts tool-call arguments for action dispatch

Recent fixes: `close()` now tears down HTTP client, session re-creation on error.

### OpenCode Skill Proposal

A skill that wraps bridge actions as OpenCode tools:
- Leverages OpenCode's configured model + memory + web search
- But introduces latency from double-routing
- Bridge's own loop is more specialized for Minecraft

### Hermes Agent Proposal

Better conceptual match than OpenCode (designed for agentic loops, tool use, planning):
- Action space abstraction aligns with our ACTION_TOOL schema
- Multi-turn planning could replace goal decomposition
- Planning/reasoning handled by Hermes

**Open questions for both**:
1. Long-running process support (hours/days)?
2. Hierarchical goal decomposition?
3. Who owns the loop — bridge or agent framework?
4. Latency overhead vs direct LLM call?

**Key decision**: Both are purely optional sidecars. The bridge must always work standalone with any supported LLM provider.

## Bug Tracking Update

**Fixed in this session**: B9 (private member `_root` in `_connect` — replaced with `_memory.save_goal()` using `root_description` property), B10 (no `_parent_ref` in `set_goal_from_subgoals`), B11 (hardcoded 2s botsummon delay replaced with polling), B12 (memory deduplication), B18 (orchestrator `_connect` still accessed `_goals._root` directly — now uses `root_description` property)

**New bugs tracked**: none discovered this session.

## Known Gaps

1. **Chat command polling** (`chat_commands.py`): The `poll()` method doesn't have a reliable way to read in-game chat from MCPQ. The current implementation is a stub that checks `mc.get_chat_log()` if available. A proper implementation needs either MCPQ's chat listener API or a side-channel.
2. **Inventory parsing** (`observer.py` `_parse_inventory_nbt`): The NBT parser handles the standard format but may break on modded items or special edge cases (empty slots, zero-count stacks). Consider adding error logging for unparseable entries.
3. **Structure detection**: Currently only at the prompt level. No automated structure detection or known-structure registry in memory yet.
4. **WASD movement**: Still in planning phase. Not implemented.

## Key Files Modified

| File | Changes |
|------|---------|
| `bridge/memory.py` | SQLite persistence: `_init_db()`, `_save_fact_to_db()`, `_load_facts_from_db()`, `save_goal()`, `close()` |
| `bridge/goal_manager.py` | Added `root_description` property |
| `bridge/chat_commands.py` | New file — `ChatCommandHandler` with 7 commands |
| `bridge/inventory_manager.py` | New file — structured inventory queries |
| `bridge/orchestrator.py` | Integrated N3/N4/N1; fixed private member access |
| `llm/prompts.py` | Rules 11-13 (structure respect); biome in `format_state()` |
| `docs/features/opencode-skill.md` | Expanded Hermes Agent section; decision statement |
| `docs/agent-diary/2026-05-13-phase4-6-features.md` | This file |
