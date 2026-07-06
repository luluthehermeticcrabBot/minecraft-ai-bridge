# Planned Features

> Last updated: 2026-05-13

This directory contains detailed proposals for new features. Each feature has its own `.md` file with scope, design, implementation plan, and open questions.

## Navigation

| Priority | Feature | Description | Est. Effort |
|----------|---------|-------------|-------------|
| **P0** | — | Critical bug fixes | Done |
| **P1** | N4 | **Chat Command Interface** — human-in-the-loop control via in-game chat | 4-6h |
| **P1** | N3 | **Persistent Memory Database** — SQLite-backed cross-session memory | 4h |
| **P2** | N1 | **Structured Inventory Manager** — parsed inventory with tools/durability tracking | 4-6h |
| **P2** | N2 | **WASD Movement System** — human-like walking movement (not /tp) | ✅ **Done (v0.5.0)** |
| **P2** | N5 | **Visual Perception** — screenshots + vision LLM for world understanding | 1-2 days |
| **P3** | N6 | **Blueprint System** — pre-defined building plans | 3-5 days |
| **P3** | N7 | **Redstone Engineering** — redstone component placement & circuits | 5-7 days |
| **P3** | N8 | **Villager Trading** — find, trade with villagers | 3-5 days |
| **P3** | N9 | **Multi-Agent Coordination** — multiple bots sharing goal tree | 1-2 weeks |
| **P3** | N10 | **Web Dashboard** — FastAPI + HTMX monitoring UI | 3-5 days |

## Survival Mode Roadmap

```
Phase 1 [NOW]     ─ Movement via teleportation (MVP)
Phase 2 [NEXT]    ─ WASD movement + collision detection
Phase 3 [SOON]    ─ Survival crafting (recipes, tables)
Phase 4 [FUTURE]  ─ Hunger, health, armor management
Phase 5 [FUTURE]  ─ Mob hunting + defense
Phase 6 [FUTURE]  ─ Complete survival autonomy
```

## Structure Preservation

A key design constraint: the agent MUST respect existing player-built structures.
- No building over or within 5 blocks of player-built blocks
- No modifying NPC village buildings unless explicitly instructed
- Railroad and infrastructure corridors preserved
- Implementation: "known structures" layer in memory that scan-for-buildings populates

See `wasd-movement.md` for how structure preservation impacts the movement system.
