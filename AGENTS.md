# AGENTS.md — AI Handoff Notes

> This file is for AI agents working on this project. It captures what's been done, what needs work, design decisions, and conventions.

## Project Overview

**Minecraft AI Bridge** — an LLM-powered agent that plays Minecraft by connecting to a Paper server via the MCPQ plugin (gRPC). No game client needed. The agent receives high-level goals, decomposes them, then runs a think-act-observe loop using an LLM (OpenAI/Anthropic/Ollama/OpenRouter/OpenCode Server) to decide actions.

- **Language**: Python 3.11+
- **Async**: asyncio throughout
- **Config**: pydantic-settings (YAML + env vars)
- **Package**: `minecraft-ai-bridge` (PyPI-style, installable with pip)
- **Server**: Paper 1.20.1 + MCPQ plugin v2.2 + fakeplayer plugin
- **Docker**: itzg/minecraft-server image with plugins mounted

## What's Built (Complete)

### Minecraft Layer (`minecraft_ai_bridge/minecraft/`)
- `mc_api.py` — `McpqClient` async wrapper around MCPQ gRPC (all calls via `asyncio.to_thread`)
- `actions.py` — 24 `ActionType` enum values + handlers + `execute_action()` dispatcher
- `observer.py` — `Observer` + `WorldState` dataclass, concurrent observation via `asyncio.gather`
- `rcon.py` — async RCON client (optional, unmaintained — MCPQ is primary)

### LLM Layer (`minecraft_ai_bridge/llm/`)
- `client.py` — `LLMClient` ABC + 5 implementations: OpenAI, Anthropic, Ollama, OpenRouter, OpenCode Server. Factory function `create_llm_client()`. `ACTION_TOOL` schema definition.
- `prompts.py` — `SYSTEM_PROMPT` string, `format_state()`, `format_goal()`
- `models.py` — `LLMResponse`, `Message`, `Role` pydantic models

### Bridge Layer (`minecraft_ai_bridge/bridge/`)
- `orchestrator.py` — `Orchestrator` class with `run()` and `_step()` think-act-observe loop. Auto-spawns fake player on connect, teleports to safe location.
- `goal_manager.py` — `GoalNode` tree, LLM-based decomposition, fallback plans for common goals (build, mine, farm, workshop, explore, generic)
- `memory.py` — `AgentMemory` with short-term (rolling deque) and long-term (facts set) memory

### CLI (`minecraft_ai_bridge/main.py`, `__main__.py`)
- `minecraft-ai-bridge [OPTIONS] [GOAL]` CLI with `--verbose`, `--config`, `--version`, `--list-providers`
- Entry point registered in `pyproject.toml`

### Config (`minecraft_ai_bridge/config.py`)
- `AppConfig` with nested `MinecraftConfig`, `MCPQConfig`, `LLMConfig`, `BridgeConfig`, `GoalConfig`
- `from_yaml()` class method merges YAML + env vars with type coercion

### Infrastructure
- `Dockerfile` — `python:3.13-slim`, pip installs the package
- `docker-compose.yml` — Paper server (itzg/minecraft-server:latest with PAPER type, 1.20.1) + bridge service. MCPQ on port 1789. Plugin mounts. Fakeplayer plugins.
- `scripts/download-plugins.sh` — downloads MCPQ v2.2 jar
- `mcpq-config/config.yml` — MCPQ bound to `0.0.0.0:1789`
- `mcpq-plugins/` — mounted plugin directory
- `.env.example`, `.gitignore`, `config.yaml`

### Documentation
- `README.md` — complete project overview
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
- **No player movement simulation**: Movement is via `/tp` commands, not walking/entity physics. OK for creative mode, less useful for survival.
- **No inventory tracking**: Inventory is read via `/data get entity @p Inventory`. The observer grabs it raw but doesn't parse into structured slots. LLM sees raw NBT.

### Paper / MCPQ
- **Paper 1.20.1 only**: MCPQ v2.2 targets 1.20.1. Upgrading MC version requires MCPQ compatibility check.
- **fakeplayer plugin**: tanyaofei/minecraft-fakeplayer v0.3.19 with CommandAPI 9.7.0. The player sometimes teleports back to original spawn coordinates — the bridge re-teleports on reconnect.
- **Plugin version pinning**: MCPQ and fakeplayer jars are downloaded from GitHub releases. If URLs change, `download-plugins.sh` needs updating.

### Docker
- **Health check timing**: First Paper startup takes 2-5 minutes. The health check has a 240s start period. The bridge retries for 20 attempts with backoff.
- **config.yaml volume mount**: Mounted read-only at `/app/config.yaml`. Changes require `docker compose restart bridge`.

### Code Quality
- **No tests**: The project has zero unit/integration tests. High priority for next session.
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

### P0: Testing
- Add unit tests for `GoalManager._fallback_decompose()` — all pattern+text combinations
- Add unit tests for `format_state()` — various WorldState configurations
- Add integration test: MCPQ connection → observe loop → actions
- Mock LLM responses for deterministic testing

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
- Set up GitHub Actions CI (lint + type check + test)
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
| `config.yaml` | Default configuration |
| `docker-compose.yml` | Paper server + bridge services |
| `docs/*.md` | Full documentation set |
| `AGENTS.md` | This file |

## Environment Info

- **Python**: 3.11+ required (built on 3.13)
- **OS**: Linux (Docker: python:3.13-slim)
- **Paper**: 1.20.1 via itzg/minecraft-server
- **MCPQ plugin**: v2.2
- **fakeplayer**: v0.3.19 + CommandAPI 9.7.0
- **Docker compose**: v2 format
