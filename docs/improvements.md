# Planned Improvements

> Last updated: 2026-05-13

## Priority Matrix

```
P0 ─ Critical ─ Must fix before stable use
P1 ─ High     ─ Significant quality-of-life or correctness win
P2 ─ Medium   ─ Valuable but not blocking
P3 ─ Low      ─ Nice-to-have
```

## P0 — Critical

| ID | Description | Effort | Status |
|----|-------------|--------|--------|
| I1 | Fix all confirmed bugs (see `bugs.md`) | Done | ✅ Complete |

## P1 — High

| ID | Description | Effort | Status |
|----|-------------|--------|--------|
| I2 | **Parse inventory NBT into structured data** | 2-4h | ✅ Done — `InventorySlot`, `_parse_inventory_nbt()`, `WorldState.inventory` |
| I3 | **Parse health as float** | 30m | ✅ Done — `_parse_nbt_value()` in `observer.py` |
| I4 | **Add biome detection** | 2-4h | ✅ Done — `McpqClient.get_biome()`, exposed via `WorldState.biome` |
| I5 | **Safe string formatting** | 15m | ✅ Done — `string.Template` in all LLM clients |
| I6 | **Error loop protection** — consecutive failures → graceful shutdown | 30m | ✅ Done — failure counter + backoff |
| I7 | **Better type annotations** — `Handler = callable` → proper type | 15m | ✅ Done — `Callable[..., Awaitable[ActionResult]]` |
| I8 | **RCON deprecation** — mark as deprecated in docs | 15m | ✅ Done — header comment and doc note |
| I9 | **Pre-commit hooks** — ruff + mypy pre-commit config | 1h | ✅ Done |
| I10 | **GitHub Actions CI** — lint + type check + test workflow | 2h | Pending |
| | I11 | **Ollama compatibility** — graceful fallback for JSON mode | 1h | ✅ Done |
| I12 | **Configurable botsummon retry** — polling loop | 30m | ✅ Done — 10-attempt polling at 1s intervals |
| I13 | **Memory deduplication** — skip unchanged observations | 30m | ✅ Done — summary comparison in `record_observation()` |

## P1 — New (Phase 4)

| ID | Description | Effort | Status |
|----|-------------|--------|--------|
| I25 | **Persistent memory (SQLite)** — facts survive agent restarts | 2h | ✅ Done — `AgentMemory` now optionally SQLite-backed |
| I26 | **In-game chat commands** — `!status` `!stop` `!goal` `!goto` `!follow` `!come` | 3h | ✅ Done — `ChatCommandHandler` module |
| I27 | **Structured inventory manager** — `has_item()`, `count_item()`, `get_summary()` | 2h | ✅ Done — `InventoryManager` module |
| I28 | **Structure respect rules** — prompt guidance to not build over existing builds | 1h | ✅ Done — `SYSTEM_PROMPT` rules 11-13 |

## P2 — Medium

| ID | Description | Effort | Notes |
|----|-------------|--------|-------|
| I14 | LLM context window optimization — summarize long-term facts instead of dumping raw | 2h | Reduces token usage |
| I15 | Add "last action failed because..." hints to help LLM recover | 1h | Improves robustness |
| I16 | Retry with different params when action fails | 2h | Smart error recovery |
| I17 | Add `__bool__` to `ActionResult` for cleaner checks | 15m | Code clarity |
| I18 | Graceful shutdown on SIGTERM/SIGINT | 1h | Docker friendliness |
| I19 | Log rotation / structured logging | 2h | Better debugging |

## P3 — Low

| ID | Description | Effort | Notes |
|----|-------------|--------|-------|
| I20 | Health check endpoint for bridge | 2h | Docker orchestration |
| I21 | `mypy` strict mode configuration | 1h | Type safety |
| I22 | PyPI publishing pipeline | 4h | Distribution |
| I23 | Add `__all__` to all public modules | 1h | API cleanliness |
| I24 | Config schema generation (JSON Schema from pydantic) | 2h | IDE support |

## Implementation Notes

### I2 — Structured Inventory
The raw NBT from `/data get entity @p Inventory` looks like:
```json
[{id:"minecraft:dirt",Count:64b,Slot:0b},{id:"minecraft:stone",Count:32b,Slot:1b}]
```
Parse into `list[InventorySlot(id, count, slot)]` and expose via `WorldState.inventory`.

### I4 — Biome Detection
Options (in order of preference):
1. MCPQ's `WorldInfo` or `Chunk` API if available
2. Surface block heuristics (grass → plains, sand → desert, etc.)
3. Seed + chunk coordinate → biome mapping (needs seed knowledge)
4. Accept `/locate biome` noise with filtering
