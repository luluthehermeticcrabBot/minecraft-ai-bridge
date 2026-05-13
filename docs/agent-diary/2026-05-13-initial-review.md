# Agent Diary — Initial Codebase Review &amp; Bug Fixes

**Date:** 2026-05-13  
**Agent:** OpenCode Orchestrator  
**Model:** big-pickle  

## Summary

Initial comprehensive review of the Minecraft AI Bridge codebase. Reviewed every source file in the project (~2600 lines of Python + docs) and identified:

- **6 confirmed bugs** (1 critical, 3 gameplay, 2 maintenance)
- **13 improvement areas**
- **10 new feature proposals**

## Bugs Fixed (Phase 1)

| ID | Description | File | Fix |
|----|-------------|------|-----|
| B1 | `turn_left`/`turn_right` missing space — teleports 90 blocks instead of rotating | `actions.py:161,171` | Added space after z-coordinate arg so `~-90` is parsed as yaw rotation |
| B2 | `craft_item` silently uses `/give` (creative-only) | `actions.py:272` | Added try/except with clear error message, documented creative-mode dependency |
| B3 | `drop_item` uses `/clear` which deletes items instead of dropping them | `actions.py:284` | Now spawns an item entity via `/summon` at player position after clearing from inventory |
| B4 | Goal tree parent tracking uses string comparison instead of object references | `goal_manager.py:249-270` | Added `_parent_ref` attribute to `AgentGoal`, rewrote `mark_current_complete` to navigate by reference |
| B5/B6 | OpenCodeServerClient session never closed, never re-created on restart | `client.py:817`, `orchestrator.py:353` | Added `close()` call in `_disconnect()`, session reset on close |
| B8 | Private member access `_goals._root` in orchestrator log | `orchestrator.py:86` | Added `sub_goal_count` property to `GoalManager` |

## Design Decisions

1. **Parent reference via private attribute**: Chose `_parent_ref` (a private, non-serialized attribute on `AgentGoal`) instead of changing `parent_goal` to an object reference. This keeps the Pydantic model clean for potential serialization while fixing the tree navigation bug.

2. **RCON deprecated, not removed**: Added module-level `.. deprecated::` docstring directive. The file stays for admin-command fallback but is clearly marked as unmaintained.

3. **`craft_item` kept as action name**: Rather than renaming to `give_item` (which would break existing LLM training data / tool schemas), we documented the limitation. A proper survival crafting system is tracked as a planned feature.

## Priority for Next Session

- Phase 3: Parse inventory NBT into structured data (I2) — biggest LLM quality win
- Phase 4: Chat command interface (N4) — enables human-in-the-loop control
- Phase 5: WASD movement research + planning
