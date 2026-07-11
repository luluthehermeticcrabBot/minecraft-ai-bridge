# AGENTS.md — AI Handoff Notes

> This file is for AI agents working on this project. It captures what's been done, what needs work, design decisions, and conventions.

## Project Overview

**Minecraft AI Bridge** — an LLM-powered agent that plays Minecraft by connecting to a Paper server via the MCPQ plugin (gRPC). No game client needed. The agent receives high-level goals, decomposes them, then runs a think-act-observe loop using an LLM (OpenAI/Anthropic/Ollama/OpenRouter/OpenCode Server) to decide actions.

- **Language**: Python 3.11+
- **Async**: asyncio throughout
- **Config**: pydantic-settings (YAML + env vars)
- **Package**: `minecraft-ai-bridge` (PyPI-style, installable with pip)
- **Server**: Paper 1.21.4 + MCPQ plugin v2.2 + fakeplayer plugin
- **Docker**: itzg/minecraft-server image with plugins mounted

## What's Built (Complete)

### Minecraft Layer (`minecraft_ai_bridge/minecraft/`)
- `mc_api.py` — `McpqClient` async wrapper around MCPQ gRPC (all calls via `asyncio.to_thread`)
- `actions.py` — 25 `ActionType` enum values + handlers + `execute_action()` dispatcher (including `sprint` + A*-powered `walk_to`)
- `pathfinding.py` — A* pathfinder that scans a walkability grid via MCPQ `getBlock` and returns waypoints
- `observer.py` — `Observer` + `WorldState` dataclass, concurrent observation via `asyncio.gather`
- `rcon.py` — async RCON client (optional, unmaintained — MCPQ is primary)

### LLM Layer (`minecraft_ai_bridge/llm/`)
- `client.py` — `LLMClient` ABC + 5 implementations: OpenAI, Anthropic, Ollama, OpenRouter, OpenCode Server. Factory function `create_llm_client()`. `ACTION_TOOL` schema definition.
- `prompts.py` — `SYSTEM_PROMPT` string, `format_state()`, `format_goal()`
- `models.py` — `LLMResponse`, `Message`, `Role` pydantic models

### Bridge Layer (`minecraft_ai_bridge/bridge/`)
- `orchestrator.py` — `Orchestrator` class with `run()` and `_step()` think-act-observe loop. Auto-spawns fake player on connect, teleports to safe location.
- `goal_manager.py` — `GoalNode` tree, LLM-based decomposition, fallback plans for common goals (build, mine, farm, workshop, explore, generic). Mining pattern uses `\bore\b` to avoid matching "Explore" via substring.
- `memory.py` — `AgentMemory` with short-term (rolling deque) and long-term (facts set) memory
- `chat_commands.py` — Incoming chat command parser (`!stop`, `!status`, `!follow`) for live agent control
- `inventory_manager.py` — Structured inventory slot tracking with NBT parsing

### CLI (`minecraft_ai_bridge/main.py`, `__main__.py`)
- `minecraft-ai-bridge [OPTIONS] [GOAL]` CLI with `--verbose`, `--config`, `--version`, `--list-providers`
- Entry point registered in `pyproject.toml`

### Config (`minecraft_ai_bridge/config.py`)
- `AppConfig` with nested `MinecraftConfig`, `MCPQConfig`, `LLMConfig`, `BridgeConfig`, `GoalConfig`
- `from_yaml()` class method merges YAML + env vars with type coercion

### Infrastructure
- `Dockerfile` — `python:3.13-slim`, pip installs the package
- `docker-compose.yml` — Paper server (itzg/minecraft-server:latest with PAPER type, 1.21.4) + bridge service. MCPQ on port 1789. Plugin mounts. Fakeplayer plugins. OPS env var with operator usernames.
- `scripts/download-plugins.sh` — downloads MCPQ v2.2 jar
- `mcpq-config/config.yml` — MCPQ bound to `0.0.0.0:1789`
- `mcpq-plugins/` — mounted plugin directory
- `.env.example`, `.gitignore`, `config.yaml`

### Documentation
- `README.md` — complete project overview
- `ROADMAP.md` — current priorities, completed milestones, release plan
- `docs/ARCHITECTURE.md` — 3-layer architecture deep dive
- `docs/SETUP.md` — installation guide (Docker + local)
- `docs/CLI.md` — CLI reference
- `docs/AGENT.md` — agent internals (loop, actions, goals, memory)
- `docs/EXTENDING.md` — how to extend actions, providers, etc.
- `this file` — AGENTS.md handoff notes

## Known Issues & Limitations

### Critical
- **Model compatibility**: Some OpenRouter models (esp. newer ones like `gpt-5-nano`) may not support tool calling. Test with models known to work: `openai/gpt-4o-mini`, `openai/gpt-4o`, `anthropic/claude-sonnet-4`.
- **No entity for MCPQ**: If the fakeplayer isn't spawned on connect, MCPQ player ops fail. The orchestrator has retry logic but it's not 100% reliable.

### Performance
- **Scanner limited to radius 16**: The `scan` action caps at r=16 to avoid MCPQ rate limiting. For scanning large areas, needs chunk-based iteration.
- **Movement system**: Step-by-step WASD-like movement via execute-based commands with collision detection, hazard avoidance, and A* pathfinding. Slow for very long distances (>50 blocks falls back to teleport).
- **Inventory tracking**: Inventory parsed into structured `InventorySlot` objects; observer grabs via `/data get entity @p Inventory` and inventory manager tracks slots.

### Paper / MCPQ
- **Paper 26.1.2** (Mojang YY numbering, April 2026): MCPQ v2.2 works. Paper API 26.1.2.build.63-stable.
- **Bot plugin**: Custom `mc-bot-plugin-1.0.0.jar` replaces tanyaofei/fakeplayer. Built in `bot-plugin/` (Maven, Java 25). Provides `/botsummon <name>` command that creates a ServerPlayer entity MCPQ can detect.
- **Plugin version pinning**: MCPQ jar is downloaded from GitHub releases. The bot plugin is built locally.
- **Known Paper 26.1.2 issues**:
  - `time query daytime` throws CommandException — use `time query day` instead (fixed in bridge code)
  - `setblock` commands via MCPQ may have array-related issues (mitigated in MCPQ client)
  - `defaultgamemode` command format changed (use `gamemode` instead)

### Docker
- **Health check timing**: First Paper startup takes 2-5 minutes. The health check has a 240s start period. The bridge retries for 20 attempts with backoff.
- **config.yaml volume mount**: Mounted read-only at `/app/config.yaml`. Changes require `docker compose restart bridge`.

### Code Quality
- **Tests**: 182 tests total (160 unit + 22 integration). Unit tests use `MockMcpqClient` for deterministic MCPQ simulation. Integration tests use a real MCPQ server + real LLM (OpenRouter `openai/gpt-oss-20b`) for end-to-end validation. All tests run against Paper 26.1.2. Run with `pytest tests/`.
- **No type checking in CI**: `pyproject.toml` has dev deps for mypy/ruff but no CI setup.
- **gRPC stubs are synchronous**: MCPQ generated stubs block; dispatched via `asyncio.to_thread`. Not ideal but works.
- **RCON client is unmaintained**: Since the MCPQ migration, `rcon.py` isn't tested. Consider removing or marking deprecated.

## Design Decisions Made

### Why MCPQ over RCON?
MCPQ gives structured world manipulation (setBlock, getBlock, getPlayerPos) that RCON can't do. RCON only allows running commands and parsing string output.

### Why fakeplayer over pyCraft?
pyCraft maxes at Minecraft 1.18.1 (protocol 754) and is unmaintained. fakeplayer creates a ServerPlayer server-side only — no network protocol needed.

### Why asyncio?
The bridge is I/O-bound (LLM API calls, MCPQ gRPC, rate-limit delays). asyncio allows concurrent observation queries without thread overhead.

### Why docker-compose?
Simplifies the Paper setup (plugin downloads, config mounting, network). The itzg/minecraft-server image handles Paper installation automatically.

### Why hardcoded fallback plans?
Some LLMs (especially smaller/local ones) can't reliably output structured JSON for goal decomposition. Fallback plans ensure the bridge works without a high-quality LLM.

## Priority Work Items

### P0: None (Testing Complete)
The 0.5.0 release completed the testing milestone:
- **Unit tests** (190): MockMcpqClient covers all 24 actions, observer parsing, memory, goal fallback plans, config, inventory manager, chat commands, pathfinding
- **Integration tests** (22): Full think-act-observe loop with real MCPQ server + real LLM inference (OpenRouter `openai/gpt-oss-20b`). Covers teleport, exploration, disconnect handling, fallback decomposition, failure counting, memory recording, chat command stop, and inventory creation.
- **Goal-verification assertions**: Integration tests verify agent behavior via:
  - `action_taken(orch, *names) → bool` — checks if the agent performed a specific action (parses `MemoryEntry.raw`)
  - `actions_taken(orch) → list[str]` — all action names from short-term memory
  - `position_reached(orch, x, y, z, tolerance) → bool` — checks observations for target coordinates
  - These helpers are essentially free (in-memory dict parsing, no extra I/O)
- **Real LLM tests**: 9/12 integration tests use real OpenRouter inference; 3 use `MockLLMClient` for deterministic edge cases (fallback plans, failure counting)

### P1: Observer Improvements
- Parse inventory NBT into structured slot data (not raw command output)
- Parse health numeric value from `/data get entity @p Health`
- Add biome detection (without the noisy `/locate biome` command — maybe via client seed + chunk coordinates)

### P2: LLM Prompt Optimization
- Trim context window: long-term memory should be summarized, not dumped raw
- Add "last action failed because..." hints to help the LLM recover
- Implement retry with different params when action fails

### P3: Player Movement
- Replace `/tp` with WASD-style movement simulation for survival mode
- Maybe control through MCPQ if the plugin adds it, or use Minecraft's `/execute` with `facing` + `move`

### P4: Infrastructure
- Set up GitHub Actions CI (lint + type check + test) — **partial**: CI runs lint + unit tests on every PR; integration tests gated on `OPENROUTER_API_KEY` secret. See `.github/workflows/ci.yml`.
- Re-enable `mypy` in CI — **tracking**: mypy is currently skipped due to strict OpenAI/Anthropic SDK type signatures in `llm/client.py`. Job is wired up but no-op until `MYPY_ENABLED` repo variable is set. Track re-enablement as a follow-up issue.
- Add `mypy` configuration to `pyproject.toml`
- Consider adding `pre-commit` hooks
- Publish to PyPI as `minecraft-ai-bridge`

## Code Conventions

- **Imports**: standard library → third-party → local. Absolute imports preferred (`from .module import X`).
- **Type hints**: use `from __future__ import annotations` everywhere. Full type annotations required.
- **Logging**: use `logger = logging.getLogger(__name__)` per module. No print statements.
- **Error handling**: catch specific exceptions, not `Exception`/`BaseException`. Log with `logger.exception()` for traceback.
- **Async patterns**: all IO is async. gRPC sync calls via `asyncio.to_thread`. LLM HTTP via `httpx.AsyncClient` or `openai.AsyncOpenAI`.
- **Config**: pydantic models with `SettingsConfigDict(env_prefix=...)`. `field_validator` for fallback env vars.
- **Dataclasses**: use `@dataclass` for simple data containers, `BaseModel` (pydantic) for validated config.

## Key File Map

| File | Purpose |
|------|---------|
| `minecraft_ai_bridge/main.py` | CLI entry point, argument parsing |
| `minecraft_ai_bridge/config.py` | All config models and YAML/env loading |
| `minecraft_ai_bridge/minecraft/mc_api.py` | MCPQ gRPC client wrapper |
| `minecraft_ai_bridge/minecraft/actions.py` | ActionType enum + 24 handlers + dispatcher |
| `minecraft_ai_bridge/minecraft/observer.py` | World state observation |
| `minecraft_ai_bridge/minecraft/rcon.py` | RCON client (legacy, unused) |
| `minecraft_ai_bridge/llm/client.py` | LLMClient ABC + 5 providers + ACTION_TOOL |
| `minecraft_ai_bridge/llm/prompts.py` | System prompt, state formatting |
| `minecraft_ai_bridge/llm/models.py` | LLMResponse, Message, Role models |
| `minecraft_ai_bridge/bridge/orchestrator.py` | Main agent loop, connection, step logic |
| `minecraft_ai_bridge/bridge/goal_manager.py` | Goal tree, LLM decomposition, fallback plans |
| `minecraft_ai_bridge/bridge/memory.py` | Short+long term memory |
| `minecraft_ai_bridge/bridge/chat_commands.py` | Incoming chat command parser (!stop, !status, !follow) |
| `minecraft_ai_bridge/bridge/inventory_manager.py` | Structured inventory slot tracking |
| `config.yaml` | Default configuration |
| `docker-compose.yml` | Paper server + bridge services |
| `docs/*.md` | Full documentation set |
| `tests/conftest.py` | MockMcpqClient, MockLLMClient, test fixtures |
| `tests/test_*.py` | Unit + integration tests (212 total: 190 unit + 22 integration) |
| `AGENTS.md` | This file |

## Environment Info

- **Python**: 3.11+ required (built on 3.13)
- **OS**: Linux (Docker: python:3.13-slim)
- **Paper**: 1.21.4 via itzg/minecraft-server
- **MCPQ plugin**: v2.2
- **fakeplayer**: v0.3.19 + CommandAPI 9.7.0
- **Docker compose**: v2 format

## Test Infrastructure

### MockMcpqClient (`tests/conftest.py`)
Full in-memory MCPQ mock simulating a 3D world. Methods:
- `set_position()`, `set_block()`, `set_block_map()` — configure the world
- `set_inventory()`, `set_time()`, `set_players()`, `set_biome()`, `set_player_nbt()` — configure state
- `commands_ran`, `chat_messages_sent`, `last_command()` — assert on actions
- `assert_command_contains(substring)`, `assert_chat_contains(substring)` — convenience assertions

### MockLLMClient (`tests/conftest.py`)
Returns pre-configured action queues. Supports:
- `responses: list[tuple[str, dict]]` — ordered action responses
- `set_decompose_return(subgoals)` — override goal decomposition
- `prompts_received` — introspection of prompts sent

### Goal-Verification Assertions
Helpers in `tests/test_integration.py`:
- `actions_taken(orch) → list[str]` — all actions from short-term memory
- `action_taken(orch, *names) → bool` — whether any given action was taken
- `position_reached(orch, x, y, z, tol) → bool` — whether observations show target coords

### Test Organization
| Directory | Tests | Description |
|-----------|-------|-------------|
| `tests/test_actions.py` | ~90 | All 24 action handlers with MockMcpqClient |
| `tests/test_observer.py` | ~30 | NBT parsing, inventory parsing, observation formatting |
| `tests/test_memory.py` | ~15 | Short/long-term memory, dedup, persistence |
| `tests/test_goal_manager.py` | ~10 | Goal decomposition, fallback plans patterns |
| `tests/test_chat_commands.py` | ~10 | Chat command parsing and dispatch |
| `tests/test_inventory_manager.py` | ~5 | Inventory manager slot tracking |
| `tests/test_integration.py` | 12 | Full agent loop with real MCPQ + real LLM |
