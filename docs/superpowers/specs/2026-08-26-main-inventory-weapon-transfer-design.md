# Main-Inventory Weapon Transfer Design

**Date:** 2026-08-26
**Status:** Draft for user review

## Problem

`equip_best_weapon` currently selects supported weapons from hotbar slots only. A stronger weapon in the player's main inventory cannot be equipped safely. Minecraft's `/item replace ... from ...` operation copies into a destination; it does not provide an atomic two-slot swap. Copying directly into `weapon.mainhand` can discard the currently selected stack, while copying into `hotbar.0` assumes slot 0 is selected and can overwrite unrelated items.

The next equipment slice must support main-inventory candidates without losing useful items and must respect the actual `SelectedItemSlot` value.

## Goals

1. Select the strongest supported melee weapon from hotbar slots `0-8` and main-inventory slots `9-35`.
2. Preserve both the selected stack and the weapon source stack whenever a safe temporary slot is available.
3. Allow destructive overwrite only for an explicitly disposable item and only when the active goal does not need it.
4. Refuse unsafe transfers without changing inventory.
5. Handle malformed inventory records without raising or producing false selection results.
6. Preserve existing LLM action schema and `ActionResult` failure semantics.
7. Verify command syntax and selected-slot behavior against a real Paper/MCPQ server when the bot plugin is available.

## Non-goals

- Armor management, offhand loadouts, or general inventory sorting.
- Silent deletion of valuable or goal-relevant stacks.
- Treating nonzero item damage as proof that a weapon is broken; `InventorySlot` has no max-durability field.
- Adding a new dependency or modifying generated MCPQ stubs.
- Relying on a hardcoded `hotbar.0` destination.

## Design

### Candidate selection

Extend the existing pure selector to accept valid hotbar and main-inventory records:

- Hotbar: NBT slots `0-8`.
- Main inventory: NBT slots `9-35`.
- Armor, offhand, and unknown slots are excluded.
- Records with missing attributes, non-string item IDs, boolean/non-integer slots or counts, non-positive counts, or unsupported item IDs are skipped.
- Existing material ranking and lower-slot tie-breaking remain unchanged.
- Nonzero `damage` remains metadata-only until max-durability data is available.

The selector returns the original `InventorySlot`, including its NBT slot, so the transfer layer can map the source precisely.

### Slot mapping

Use explicit command-slot mapping rather than assuming NBT and command slots are interchangeable:

- NBT `0-8` maps to command slot `hotbar.0-hotbar.8`.
- NBT `9-35` maps to the corresponding player `container.0-container.26` slot using `container.(nbt_slot - 9)`.
- The current held destination is `weapon.mainhand`; `SelectedItemSlot` identifies which hotbar slot it represents.

The mapping is a named helper with boundary tests for slots `0`, `8`, `9`, and `35`; all other slots return no mapping.

### Transfer transaction

Before mutation, read inventory and selected-slot state together as closely as possible. Revalidate that:

- the source record is still nonempty;
- the selected slot is valid `0-8`;
- the source is not already the selected slot;
- a temporary empty `container` slot exists when a lossless swap is required.

For a lossless swap, use the empty temporary container slot:

1. Copy `weapon.mainhand` to `container.temp`.
2. Copy the selected weapon source to `weapon.mainhand`.
3. Clear the original source slot.
4. Copy `container.temp` to the original source slot.
5. Clear `container.temp`.

The source command slot is either `hotbar.N` or `container.N`, based on the mapping above. The transaction preserves the selected stack and moves the selected weapon into the actual main hand without relying on slot 0.

Each command response is checked. If a later step fails, attempt the inverse sequence using the known temporary and source slots. The final `ActionResult` reports both the original failure and whether rollback succeeded; it never claims success after an unverified mutation.

### Disposable overwrite fallback

If no empty temporary slot exists, direct overwrite is allowed only when all of the following hold:

1. The destination stack belongs to a small explicit disposable allowlist.
2. The active goal and current sub-goal do not mention that item or a related material objective.
3. The source and destination are re-read immediately before mutation.
4. The action result records that a disposable stack was overwritten.

The initial allowlist is intentionally narrow. Dirt variants may qualify outside building, farming, terrain, soil, or material-gathering goals. Cobblestone, sand, gravel, wood, food, tools, weapons, armor, ores, ingots, redstone components, and goal-referenced items remain protected by default.

Goal context is supplied by the orchestrator as execution context, not exposed as an LLM-controlled permission flag. If goal context is unavailable or ambiguous, destructive overwrite is refused.

### Existing equip action

Refactor `equip_item` to use the same selected-slot-aware transfer primitive. It must no longer write unconditionally to `hotbar.0` or silently discard the current selected stack. `equip_best_weapon` uses the primitive after selection; a weapon already in `SelectedItemSlot` remains a no-op.

## Error handling

- Malformed inventory entries are skipped.
- Invalid or missing selected-slot data defaults to an unavailable/unsafe state rather than selecting slot 0 as a destructive destination.
- Known MCPQ command failure responses produce `success=False` and retain the response text.
- No temporary slot plus protected destination produces a no-op failure.
- Partial transaction failures trigger rollback and explicit partial-state reporting.
- No destructive overwrite is attempted merely because a source weapon is stronger.

## Verification

Add deterministic tests for:

- hotbar and main-inventory candidate selection;
- NBT-to-command slot mapping boundaries;
- malformed records and nonzero damage;
- selected slots `0`, `3`, and `8`;
- lossless swaps preserving both source and destination stacks;
- refusal when no temporary slot exists and the destination is protected;
- goal-aware disposable overwrite for dirt outside and inside building/farming goals;
- command failure and rollback reporting;
- preservation of existing `equip_item`, `equip_best_weapon`, and `drop_item` schema entries.

Run the focused action/inventory tests, the deterministic suite, Ruff, and `git diff --check`. When the bot plugin is buildable and mounted, run a real Paper/MCPQ smoke covering a nonzero selected slot, a main-inventory source, a preserved destination stack, a disposable overwrite, and a mid-transaction failure.
