# Changelog

All notable changes to the Minecraft AI Bridge are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## Conventions

- **Added** — new functionality
- **Changed** — changes to existing functionality
- **Fixed** — bug fixes
- **Removed** — removed features (rare; we deprecate before deleting)

Versions follow [Semantic Versioning](https://semver.org/):
`MAJOR.MINOR.PATCH`. The "Unreleased" section tracks work merged to
`master` that has not yet been tagged.

## Maintenance rule

Every PR that changes user-visible behaviour (anything beyond pure
refactor, lint, or test cleanup) MUST add a line to this file under
"## [Unreleased]". The PR description should reference the relevant
section. This is enforced by the AGENTS.md "CHANGELOG.md" rule.

---

## [Unreleased]

### Added

- **Survival series — context-aware combat** (PR #9, slice 2 of post-survival work):
  - `_MOB_THREAT_LEVELS` table in `minecraft/actions.py` — per-mob
    threat classification (`low` / `medium` / `high` / `critical`)
    for all 28 detected hostile mobs plus extras. Creeper = high,
    zombie = low, skeleton = medium, warden = critical.
  - `_MOB_BLACKLIST` frozenset — mobs the agent must never attack:
    iron_golem, villager, wandering_trader, tamed wolf, tamed cat,
    tamed parrot, tamed equines (horse, donkey, mule, llama,
    trader_llama, ocelot), friendly aquatics (axolotl, dolphin,
    turtle, squid, glow_squid, frog), neutral but not aggressive
    (fox, bee, goat, strider, armadillo), and passive farm animals
    (pig, cow, sheep, chicken, mooshroom, rabbit).
  - `_get_threat_level()`, `_is_blacklisted()`, `_should_attack()`
    helpers. `_should_attack` returns False for blacklisted OR
    critical mobs.
  - `scan_entities` action returns three new structured fields:
    `detailed` (list of `{type, threat, should_attack}` per mob),
    `blacklisted` (mobs in range that must not be attacked),
    `too_dangerous` (critical mobs in range that should trigger
    flee). Backward compatible — `mobs` and `mobs_nearby` still work.
  - **Self-preservation layer** now respects the blacklist.
    Reflex attack uses `_pick_target()` to choose the highest-threat
    attackable mob, skipping blacklisted and critical ones. Threat
    assessment counts only attackable mobs against the flee
    threshold. A critical mob in range triggers flee even alone.
  - SYSTEM_PROMPT updated to document the new scan_entities fields.
- **Survival series — auto-consume food** (PR #8, slice 1 of post-survival work):
  - `ActionType.EAT` action handler. Takes `food_item` (e.g. `bread`,
    `golden_apple`) and an optional `slot` parameter. Equips the food
    to the player's hand, applies a saturation effect via
    `/effect give @p saturation` to restore hunger immediately, and
    clears one of the food items from inventory. Headless-friendly:
    no client interaction required to consume.
  - `_FOOD_ITEMS` table in `minecraft/actions.py` — 32 edible items
    with (item_id, hunger_restored, saturation_points) entries,
    covering tier 1 (enchanted_golden_apple) through tier 7 (cake).
    Sorted by saturation, descending.
  - `_is_food()` and `_food_value()` helpers. Strips the
    `minecraft:` namespace before lookup so both `bread` and
    `minecraft:bread` are recognised.
  - **Auto-consume** in `SelfPreservationLayer` — when hunger is
    below `hunger_critical_threshold` AND the player has food in
    inventory, the layer picks the highest-saturation food and
    triggers the EAT action **without waiting for the LLM**. Closes
    the "find food and then wait for the LLM to eat it" loop that
    the v0.5.1 design had.
  - `PreservationConfig.enable_auto_consume` flag (default True).
  - SYSTEM_PROMPT updated to document the new `eat` action.
- **Survival series — hunger observation** (PR #5):
  `ActionType.CHECK_HUNGER` action handler and `WorldState.hunger`
  field. The LLM can now see its food level (0–20) and react
  accordingly. The format_state prompt includes `Hunger: N/20`.
- **Survival series — combat capability** (PR #6):
  - `ActionType.SCAN_ENTITIES` action that detects 28 common hostile
    mob types within a configurable radius (default 16, capped).
    Returns both a per-mob presence map and a flat list of detected
    mobs.
  - `attack` action now accepts a `damage_amount` parameter (default
    4, clamped to [1, 64]) and returns a structured `target_hit`
    boolean so the LLM can branch on success without parsing strings.
- **Survival series — self-preservation loop** (PR #7):
  - `SelfPreservationLayer` (new module
    `bridge/self_preservation.py`) — runs after observation, before
    the LLM thinks. Detects health drops via
    `/data get entity @p LastHurtByEntity` so environmental damage
    (fall, cactus, fire, lava, drowning) does **not** trigger a
    reflex attack.
  - **Reflex attack**: when a hostile mob is in range and the
    threat is manageable (≤ `max_fightable_mobs`, health above
    `flee_health_threshold` with ≤ 1 hostile), attack the nearest
    mob without waiting for the LLM.
  - **Reflex flee**: when the threat is too high (many hostiles,
    or low health + multiple hostiles), inject an URGENT
    "Flee to safety" sub-goal at the front of the goal list and
    defer to the LLM. The original task naturally resumes when the
    agent is safe (that's the regroup).
  - **Find-food injection**: when `state.hunger < 6`, inject an
    URGENT "Find and eat food" sub-goal (no duplicates).
  - **Memory hint**: when health < 4, record a fact so the LLM
    sees the warning in its next context window.
- **Fallback plans** in `bridge/goal_manager.py`:
  - "Find and eat food" — 9-step plan for food/hunger-related
    goals. Action-verb-specific pattern so it doesn't shadow
    the existing farm plan.
  - "Flee to safety" — 8-step plan for flee/escape/retreat
    goals. Teaches the LLM to scan for hostiles, sprint away,
    find shelter, and regroup on the original task.

### Changed

- `bridge/orchestrator.py` calls `self._preservation.evaluate(world)`
  after `_observe()` and before the LLM decides. If the layer
  returns an `ActionResult`, that result is used as the action for
  the turn and the LLM is skipped. Bookkeeping (recording, failure
  tracking, termination check) runs unchanged.
- `minecraft_ai_bridge/minecraft/mc_api.py` exposes a new
  `get_hurt_by_entity() -> bool` method that reads the
  `LastHurtByEntity` NBT field via
  `/data get entity @p LastHurtByEntity`.
- The reflex-attack path in the orchestrator no longer triggers on
  environmental damage (fall, cactus, fire, etc.). This is a
  behavioral change from the first draft of the self-preservation
  layer, which reflex-attacked on any health drop.

### Fixed

- PR #7 (initial) had a reflex attack that fired on **any** health
  drop, including fall damage, cactus damage, and lava damage.
  This caused the agent to charge a nearby mob because it tripped
  on a cactus — fixing this required a damage-source check
  (`LastHurtByEntity`) and a flee path for high-threat scenarios.

---

## [0.5.1] — 2026-07-11

### Added

- `ROADMAP.md` — current priorities, completed milestones, release
  plan, and testing strategy.
- Tracking issue #2 for re-enabling `mypy` in CI.

### Changed

- CI restructured: `lint`, `Unit Tests`, and `Integration Tests`
  jobs run separately. Unit tests run on every PR; integration
  tests run on pushes to `main`/`master` with the
  `OPENROUTER_API_KEY` secret configured.
- 54 pre-existing `ruff check` warnings resolved (44 auto-fixed,
  10 manual). `ruff check`, `ruff format`, and `ruff check
  --select I` are now all clean.
- `ActionType` and `Role` migrated from `(str, Enum)` to
  `StrEnum` (Python 3.11+ idiom, ruff UP042). `str(X.MEMBER)` now
  returns the value instead of the name — no existing call sites
  depend on the name form.
- `_move_forward` no longer auto-steps over hazards (lava, fire,
  cactus, etc.). Real safety fix.
- Stale test assertions (`test_turn_left/right/jump`,
  `test_move_forward_hazard`) updated to match current command
  format. These were silently failing on master before the fix.

### Removed

- `RCONDisconnected` exception renamed to
  `RCONDisconnectedError` to satisfy `ruff` N818 (Error suffix).
  The class is internal to `rcon.py` (no usages outside the file)
  and `rcon.py` is documented as unmaintained, so this is a
  internal-only rename.

---

## [0.5.0] — 2026-07-06

### Added

- A* pathfinding for human-like walking via
  `minecraft_ai_bridge/minecraft/pathfinding.py`.
- Sprint action for faster forward movement (1.0-block steps
  with reduced collision checking).
- Execute-based WASD movement — replaces teleport-based movement
  with physics-based step-by-step walking that respects collisions
  and avoids hazards.
- Ollama fallback: when JSON mode is rejected, the Ollama client
  retries without forced JSON format instead of failing the
  request.
- 160 unit tests covering the full action surface (up from ~30
  in v0.4.0).
