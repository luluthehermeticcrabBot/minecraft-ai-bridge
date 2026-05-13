# Respecting Pre-Existing Structures

**Status:** Planning / Prompt-level only  
**Priority:** High  
**Dependencies:** Scanner (existing), coordinate awareness  

## Goal

Prevent the agent from damaging or building over player-made structures
and NPC villages unless explicitly instructed otherwise by the user.

## Current Implementation

Structure respect rules are encoded in the LLM system prompt
(see `minecraft_ai_bridge/llm/prompts.py`, rules 11-13):

- Scan before placing blocks
- Check for artificial blocks (planks, glass, doors, beds, rails, etc.)
- Do not modify NPC village buildings
- Preserve infrastructure (railroads, bridges, paths)
- Build around existing structures at a reasonable distance

## Planned Enhancements

### Level 1: Prompt Guidance (DONE)
- [x] Add structure respect rules to SYSTEM_PROMPT
- [x] Integrate into action descriptions

### Level 2: Scanning Before Building (NEXT)
- [ ] Before `place_block` or `break_block`, the agent must `scan` with
      an appropriate radius
- [ ] If the target area contains "suspicious" blocks (wood planks,
      glass panes, beds, doors, rails, etc.), ask for confirmation
- [ ] Store a "construction zone" set of coords in memory

### Level 3: Known-Structure Registry
- [ ] Maintain a set of `known_structures` in AgentMemory/long-term facts
- [ ] When the agent encounters a village, store its bounding box
- [ ] When the agent encounters a railroad, store its path segments
- [ ] Add `StructureDetector` module that analyses scan data for
      artificial patterns

### Level 4: Automated Structure Detection
- [ ] Scan a 16×16 area for "village-like" block patterns
      (workstations, beds, doors in groups)
- [ ] Flag detected structures in the WorldState
- [ ] Auto-exclude flagged areas from build actions
- [ ] Detect railroads: rails + consistent path pattern
- [ ] Detect player bases: enclosed spaces with chests, furnaces, beds

## Implementation Notes

- The scanner currently caps at r=16. A village-level scan would need
  chunk-based iteration (see scan radius limitation in known issues).
- Block type checking is cheap via MCPQ — one `getBlock` call per coord.
- Structure detection should be a best-effort flag, not a guarantee.
- The "respect" rules can always be overridden by the user via the goal
  prompt (e.g., "Build a house in that village").
