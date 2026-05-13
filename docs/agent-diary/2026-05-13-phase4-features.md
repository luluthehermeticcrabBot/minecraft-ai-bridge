# Agent Diary — Phase 4: New Features Implementation

**Date:** 2026-05-13  
**Agent:** OpenCode Orchestrator  
**Model:** big-pickle  
**Session:** Phase 4 new features (N3, N4, N1) + structure respect + WASD planning

## Summary

Implemented three major new features, expanded docs for WASD/survival mode,
and added structure-respect rules to the system prompt.

## Changes Made

### N3: Persistent Memory (`bridge/memory.py`)
- Added SQLite-backed persistence for long-term facts
- New table: `agent_facts` (deduped by unique fact text)
- New table: `agent_goals` (records goal descriptions across runs)
- Facts survive agent restarts (loaded on `__init__`, saved on `remember_fact`)
- Env var `AGENT_MEMORY_DB` to configure path (default: in-memory only)
- Uses WAL mode + thread-local connections for safety
- Added `close()` method (WAL checkpoint) and `clear_all()` 
- `save_goal()` for recording goals in DB

### N4: Chat Command Interface (`bridge/chat_commands.py`)
- New module: `ChatCommandHandler` — parses in-game `!commands`
- Polls chat via MCPQ `get_chat_log()` with fallback for bare servers
- `!status` — reports goal, turn count, position, health
- `!stop` — sets `_stop_requested` flag, graceful shutdown
- `!goal <...>` — re-assigns goal mid-session, clears short-term memory
- `!goto <player>` — teleports agent to named player
- `!follow <player>` — agent follows player (teleports each turn)
- `!come` — teleports speaker to agent's position
- `!help` — lists available commands
- Integrated into orchestrator: `poll()` called each turn, follow-mode in `_step()`

### N1: Inventory Manager (`bridge/inventory_manager.py`)
- New module: `InventoryManager` — structured inventory on top of `InventorySlot`
- `refresh()` — fetches and parses inventory via existing `_parse_inventory_nbt()`
- `has_item(item_id, min_count)` — quick existence check
- `count_item(item_id)` — total across all slots
- `get_item_slots()` / `get_hotbar()` / `get_armor()` / `get_offhand()` — filtering
- `summary` property — compact human-readable for LLM prompt
- Refreshes every 5 turns in the orchestrator loop

### Structure Respect (prompts.py)
- Added 3 new rules (11-13) to `SYSTEM_PROMPT`:
  - Scan before placing blocks, respect existing player structures
  - Avoid modifying NPC villages unless explicitly instructed
  - Preserve infrastructure (railroads, bridges, paths)
- Created `docs/features/structure-respect.md` with 4-level implementation plan

### WASD Movement Planning (`docs/features/wasd-movement.md`)
- Expanded with 4-level implementation plan
- Level 1: Execute-based movement (replace `/tp` with `/execute as @p`)
- Level 2: Collision detection (scan target block before moving)
- Level 3: A* pathfinding for multi-block navigation
- Level 4: Survival enhancements (hunger, sprint, sneak, elytra)
- Comparison table with Mineflayer, pyCraft, Baritone

### Survival Mode Expansion (`docs/features/survival-mode.md`)
- Added risk assessment matrix (health, armor, weapon, mob count, time, biome)
- Detailed prohibited targets with reasoning (why villager/enderman/iron golem)
- Hostile mob tactical engagement table (threat, strategy, reward)
- Expanded YOLO section with model comparison table (YOLOv8n/s/m, RT-DETR)
- Training approach: finetune vs existing vs zero-shot
- ThreatDetector integration architecture (background task, async YOLO)
- False positive/negative risk mitigation table
- Training data sources + deployment considerations

## Design Decisions

1. **SQLite for memory**: Python stdlib, zero dependencies, WAL mode for concurrent safety. No need for Redis/MariaDB at this scale.

2. **Chat command via polling vs listener**: MCPQ doesn't expose a chat event stream directly (no pub/sub). Polling via chat log every turn is simpler and doesn't require a new plugin. The trade-off is latency (up to 1 turn delay for command detection).

3. **Follow-mode via teleport**: WASD-based follow will replace this once pathfinding is ready. For now, `/tp` follow is functional.

4. **Inventory refresh on interval**: Refreshing every turn would add unnecessary MCPQ calls. Every 5 turns keeps the inventory reasonably fresh.

5. **Structure respect in prompt only**: Level 1 is prompt-based because it's immediate and doesn't require code changes. Levels 2-4 (scan-before-build, structure registry, auto-detection) are tracked for future implementation.

## Known Limitations

- Chat command polling depends on MCPQ's chat log access — may not work on all server configs
- Follow-mode uses `/tp` which ignores collisions
- Structure respect is LLM-compliance-based — no code enforcement yet
- Inventory manager caches data that can be up to 5 turns stale

## Next Steps

- [ ] Implement WASD movement Level 1 (execute-based)
- [ ] Add `get_chat_log()` to MCPQ client if available
- [ ] Implement structure detection Level 2 (scan-before-build)
- [ ] Add `AGENT_MEMORY_DB` to `.env.example` and `config.yaml`
- [ ] Tests for persistent memory save/load cycle
