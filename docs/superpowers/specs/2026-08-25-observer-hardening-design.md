# Observer Hardening Design

**Date:** 2026-08-25
**Status:** Draft for user review

## Problem

The merged observer implementation already exposes structured inventory, health, and biome state, but several paths are fragile:

- Inventory parsing assumes one SNBT key order and uppercase `Count`.
- Numeric parsing can extract an unrelated number instead of the requested NBT field.
- `InventorySlot.damage` is modeled but not populated.
- Biome heuristics infer biome names from blocks that occur in many biomes.
- Biome probing can issue up to ten command checks on every observation cycle.

These failures can give the LLM confidently incorrect world state or create avoidable MCPQ load.

## Goals

1. Preserve the existing `WorldState`, `InventorySlot`, `Observer`, and MCPQ action interfaces.
2. Parse common Minecraft SNBT inventory variants robustly:
   - arbitrary compound-key order;
   - modern lowercase and legacy uppercase count keys;
   - numeric suffixes (`b`, `s`, `l`, `f`, `d`);
   - optional `Damage`/`damage` values;
   - partial validity without discarding valid neighboring entries.
3. Parse health from the named `Health` field, accept numeric suffixes, and reject invalid, negative, or non-finite values without imposing the default 20-health ceiling.
4. Treat biome names as authoritative only when an `/execute if biome` probe succeeds.
5. Bound biome probing operationally:
   - probe only a curated list of common biomes;
   - cache results by chunk coordinate;
   - cache `unknown` results as well as successful results;
   - avoid repeated probes during every `Observer.observe()` cycle.
6. Keep observer failure best-effort: one failed field must not discard the rest of a snapshot.

## Non-goals

- No new SNBT parsing dependency.
- No MCPQ protocol or generated-stub changes.
- No new public state model.
- No `/locate biome` calls.
- No heuristic claims such as `grass_block -> plains` or `sand -> desert`.
- No broad observer refactor unrelated to parsing and biome query correctness.

## Design

### Inventory parsing

Keep `_parse_inventory_nbt` as the single parser used by `Observer.observe()`. Replace positional regex assumptions with a small dependency-free parser that:

1. Extracts top-level inventory compounds while respecting quoted strings and nested braces.
2. Splits compound fields on top-level commas.
3. Normalizes keys case-insensitively.
4. Parses quoted/unquoted item IDs and suffixed numeric values.
5. Requires a valid item ID, nonnegative count, and valid slot before emitting an `InventorySlot`.
6. Parses optional damage into `InventorySlot.damage`, defaulting to zero.
7. Skips malformed compounds and continues parsing later compounds.

The existing JSON-like fallback remains available for test/simulator data, but it uses the same field normalization and validation rules.

### Health parsing

Add a field-aware parser for health output. It must match the `Health` label when present, rather than selecting the first numeric token in arbitrary command output. The observer accepts finite, nonnegative numeric values, preserving values above 20 for servers or effects that modify `generic.max_health`; malformed, negative, or non-finite values remain `None`.

Existing generic `_parse_nbt_value` behavior remains compatible for position/time and direct parser tests unless a call site needs the stricter named-field behavior.

### Biome detection and cache

`McpqClient.get_biome` becomes authoritative-only:

1. Probe the curated common-biome list with `/execute if biome <x> <y> <z> minecraft:<biome>`.
2. Return the confirmed bare biome name on marker success.
3. Return `unknown` when all probes fail or the command is unavailable.
4. Do not infer biome from surface or neighboring blocks.

`Observer` caches biome results by `(chunk_x, chunk_z)` where chunk coordinates are calculated from block coordinates using Minecraft's 16-block chunks. Both known values and `unknown` are cached. A repeated observation in the same chunk performs no new biome probes; entering a new chunk performs at most one bounded probe sequence.

`get_biome` returns `unknown` when authoritative probing cannot identify the biome. `Observer` stores that value and caches it. If the client call itself raises before returning a result, `Observer` also records `unknown` for the chunk rather than leaving a stale or heuristic value.

The cache is instance-local and naturally resets for a new observer/session. Existing best-effort behavior remains: a biome failure does not fail the complete observation.

### Imports and typing

Move parser imports to the module import section. Keep full annotations and existing dataclass conventions. Use narrowly scoped helpers for compound splitting, numeric parsing, and biome cache lookup; do not introduce a general parser framework.

## Error handling

- Invalid inventory compounds are skipped with no exception escaping the observer.
- Invalid health output produces `None` and does not affect inventory, position, time, or players.
- MCPQ biome command errors are treated as an `unknown` result and cached for that chunk.
- Existing `asyncio.gather(..., return_exceptions=True)` behavior remains unchanged.

## Verification

Add deterministic tests for:

- inventory key order, lowercase/uppercase keys, numeric suffixes, damage, malformed compounds, and partial validity;
- health label matching, suffixes, malformed output, and range rejection;
- authoritative biome success, no heuristic mapping, unknown caching, same-chunk probe suppression, and new-chunk probing;
- existing observer snapshot degradation when one field fails.

Run the focused observer/MCPQ tests, Ruff on changed Python files, and the full suite where the external Paper/MCPQ integration environment is available.
