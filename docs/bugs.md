# Known Bugs

> Last updated: 2026-05-13
> Status: Active tracking of all confirmed bugs

## Fixed

| ID | Description | Fixed in | Status |
|----|-------------|----------|--------|
| B1 | `turn_left`/`turn_right` missing space — teleports 90 blocks instead of rotating | `actions.py:161,171` | ✅ Fixed |
| B2 | `craft_item` silently uses `/give` (creative-only) — no proper survival crafting | `actions.py:272` | ✅ Documented + error handling |
| B3 | `drop_item` uses `/clear` which deletes items instead of dropping as entities | `actions.py:284` | ✅ Fixed — now spawns item entity |
| B4 | Goal tree parent tracking uses string comparison instead of object references | `goal_manager.py:249-270` | ✅ Fixed — `_parent_ref` attribute |
| B5 | OpenCodeServerClient session never re-created after server restart | `client.py:631` | ✅ Session cleared on `close()` |
| B6 | OpenCodeServerClient HTTP session never explicitly closed | `orchestrator.py:353` | ✅ Close called during `_disconnect()` |
| B7 | Config `field_validator` fights pydantic-settings env resolution | `config.py:58-80` | ✅ Fixed |
| B8 | Private member access `_goals._root` in orchestrator log | `orchestrator.py:86` | ✅ Replaced with `sub_goal_count` property |

## Known & Triaged

| ID | Description | File | Impact | Notes |
|----|-------------|------|--------|-------|
| B9 | No inventory NBT parsing — raw command output shown to LLM | `observer.py:73` | Medium — LLM wastes tokens parsing raw JSON | ✅ Fixed — `_parse_inventory_nbt()` + `InventorySlot` dataclass |
| B10 | `_damage_hit_anything()` optimistic fallback assumes success | `actions.py:318` | Low — edge case with unusual /damage output | Hard to trigger in practice |
| B11 | Turn 1 has no `_last_result` — no "last action" in context | `orchestrator.py:206` | Low — only affects first decision | Acceptable behaviour |
| B12 | No biome detection for agent | `actions.py:438-439` | Medium — agent blind to biomes | ✅ Fixed — `McpqClient.get_biome()` + `WorldState.biome` |
| B13 | Consecutive failures burn through `max_iterations` | `orchestrator.py:96-100` | Medium — wastes API calls on persistent errors | ✅ Fixed — failure counter with backoff and graceful shutdown |
| B14 | `GOAL_DECOMPOSE_PROMPT.format(goal=goal)` unsafe with `{}` in goal | `client.py:221` | Low — rare in practice but can crash | ✅ Fixed — all providers use `string.Template` |
| B15 | Ollama JSON mode forced — not all models support it | `client.py:383` | Medium — causes silent failures with incompatible models | Needs graceful fallback |
| B16 | `botsummon` retry uses hardcoded 2s sleep | `orchestrator.py:309` | Low — works but fragile | ✅ Fixed — polling loop with 10 attempts at 1s intervals |
| B17 | Memory records every observation even when nothing changed | `memory.py:57-65` | Low — wastes window slots on noise | ✅ Fixed — dedup check compares summary with last observation |
| B18 | Chat command polling depends on MCPQ chat log access | `bridge/chat_commands.py` | Medium — may not work on all server configs | Fallback path available |
| B19 | InventoryManager cache can be stale (refreshes every 5 turns) | `bridge/inventory_manager.py` | Low — delayed item awareness | Acceptable trade-off for fewer MCPQ calls |

## How to Report a Bug

Open a GitHub issue with:
1. Bug ID (if known from above)
2. Steps to reproduce
3. Expected vs actual behaviour
4. Config (provider, model, mode)
5. Relevant log output
