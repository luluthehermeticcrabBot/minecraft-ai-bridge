# Minecraft AI Bridge

> An LLM-powered agent that connects to a Paper Minecraft server via the MCPQ plugin and executes goals by observing the world, reasoning with an LLM, and manipulating the world directly — no game client needed.

## Purpose

This project lets an LLM (OpenAI, Anthropic, Ollama, OpenRouter, or OpenCode Server) **play Minecraft autonomously**. Give it a high-level goal like "Build a house" or "Mine 10 iron ore" and the agent will:

1. **Decompose** the goal into sub-tasks
2. **Observe** the world (position, blocks, inventory, time, health)
3. **Think** — decide what action to take next using the LLM
4. **Act** — execute actions via the MCPQ plugin (place/break blocks, craft items, move, teleport, etc.)
5. **Remember** — store recent actions and discoveries in short and long-term memory
6. **Repeat** — until the goal is complete

The key difference from traditional RCON-based bridges: **MCPQ gives the agent direct world-manipulation APIs** — setBlock, getBlock, setSign, teleportPlayer, runCommand, postToChat — all over gRPC. No need to parse command output strings or keep a real Minecraft client logged in.

## Architecture

```
┌──────────────────────────────────────────────────┐
│           LLM Provider (the "brain")              │
│  OpenAI · Anthropic · Ollama · OpenRouter · OC    │
│  Goal decomposition · Action selection · Reasoning │
└──────────────────────┬───────────────────────────┘
                       │ actions + observations
┌──────────────────────▼───────────────────────────┐
│           Bridge Orchestrator                     │
│  ┌─────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Think   │→ │ Act          │→ │ Observe      │ │
│  │ (LLM)   │  │ (MCPQ calls) │  │ (MCPQ calls) │ │
│  └─────────┘  └──────────────┘  └──────────────┘ │
│  ┌─────────┐  ┌──────────────┐                    │
│  │ Goals   │  │ Memory       │                    │
│  │ Manager │  │ (short+long) │                    │
│  └─────────┘  └──────────────┘                    │
└──────────────────────┬───────────────────────────┘
                       │ gRPC (protobuf)
┌──────────────────────▼───────────────────────────┐
│        Paper Server + MCPQ Plugin                 │
│  setBlock · getBlock · setSign · teleportPlayer   │
│  getPlayer · getPlayerPos · runCommandBlocking    │
│  postToChat · getTime · getNbt                    │
└──────────────────────────────────────────────────┘
```

### Three Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| **Minecraft Interface** | `minecraft_ai_bridge.minecraft` | MCPQ client wrapper, 24 action handlers, world observation (position, blocks, inventory, time, weather, health) |
| **LLM Abstraction** | `minecraft_ai_bridge.llm` | Unified interface for 5 LLM providers, tool-calling schema, system prompts |
| **Bridge Orchestration** | `minecraft_ai_bridge.bridge` | Think-act-observe loop, goal decomposition & tracking, short+long-term memory |

## Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Docker** (recommended for the Paper server) or an existing Paper 1.20.1 server
- **An LLM API key**: OpenAI, Anthropic, OpenRouter, or a local Ollama / OpenCode Server

### 2. Clone and Install

```bash
git clone <repo-url>
cd minecraft-ai-bridge

# Basic install
pip install -e .

# With Anthropic support
pip install -e ".[anthropic]"

# With dev tools
pip install -e ".[dev]"
```

### 3. Download the MCPQ Plugin

```bash
chmod +x scripts/download-plugins.sh
./scripts/download-plugins.sh
```

This downloads the MCPQ v2.2 plugin jar into `mcpq-plugins/`.

### 4. Configure

```bash
cp .env.example .env
# Edit .env with your LLM API keys and Minecraft server details

cp config.yaml config.yaml
# Edit config.yaml with your provider, model, and server settings
```

Key configuration: set `mc_api.host` and `mc_api.port` to match your MCPQ plugin endpoint, and set `llm.provider` + `llm.model` to your chosen LLM.

### 5. Start the Paper Server (Docker)

```bash
docker compose up -d minecraft
```

The first startup downloads Paper + initializes the world (2-5 minutes). Watch logs:

```bash
docker compose logs -f minecraft
```

When you see `Done (XX.XXXs)!` the server is ready.

### 6. Run the Bridge

```bash
# Via Docker (config from docker-compose.yml env vars)
GOAL="Build a small wooden house by the lake" docker compose run --rm bridge

# Or locally against a remote server
minecraft-ai-bridge "Explore and find a village"

# Verbose mode (see LLM reasoning)
minecraft-ai-bridge --verbose "Mine 10 iron ore and smelt it into iron ingots"

# Custom config file
minecraft-ai-bridge --config my-config.yaml "Build a cobblestone bridge"
```

## CLI Reference

```
usage: minecraft-ai-bridge [-h] [-c CONFIG] [--verbose] [--version] [--list-providers] [goal]

LLM-powered AI agent that plays Minecraft.

positional arguments:
  goal                  High-level goal for the AI agent (e.g., 'Build a house')

options:
  -h, --help           Show this help message and exit
  -c, --config CONFIG  Path to config YAML file (default: config.yaml)
  --verbose            Enable verbose/debug logging
  --version            Show version and exit
  --list-providers     List supported LLM providers and exit
```

### List Providers

```bash
minecraft-ai-bridge --list-providers
```

Shows all 5 supported providers, their required env vars, and model naming conventions.

## LLM Providers

| Provider | Models | Env Var | Optional Install |
|----------|--------|---------|------------------|
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` | `OPENAI_API_KEY` or `LLM_OPENAI_API_KEY` | — |
| **Anthropic** | `claude-sonnet-4-20250514`, `claude-haiku-3-5` | `ANTHROPIC_API_KEY` or `LLM_ANTHROPIC_API_KEY` | `[anthropic]` |
| **Ollama** | `llama3`, `mixtral`, any local model | `LLM_OLLAMA_BASE_URL` (default: `http://localhost:11434`) | — |
| **OpenRouter** | `openai/gpt-4o`, `anthropic/claude-sonnet-4`, 200+ | `OPENROUTER_API_KEY` or `LLM_OPENROUTER_API_KEY` | — |
| **OpenCode Server** | `big-pickle`, or `providerID/modelID` | `LLM_OPencode_SERVER_URL` (default: `http://localhost:4096`) | — |

Set `LLM_PROVIDER` and `LLM_MODEL` in your env or config.yaml to switch.

## Docker

The `docker-compose.yml` provides two services:

```bash
# Download the MCPQ plugin first
./scripts/download-plugins.sh

# Start the Paper server
docker compose up -d minecraft

# Run the bridge once
GOAL="Build a bridge" docker compose run --rm bridge

# Or run persistently (restarts on crash)
docker compose up -d bridge   # reads GOAL from docker-compose.yml or .env
```

### Environment for Docker

Set variables in `.env` at the project root:

```bash
OPENROUTER_API_KEY=sk-or-...
GOAL="Build a house"
```

Or pass inline:

```bash
LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini LLM_OPENAI_API_KEY=sk-... GOAL="Find diamonds" docker compose run --rm bridge
```

## Configuration

Configuration comes from two places, merged with **env vars taking priority**:

1. **`config.yaml`** — all settings in one file
2. **Environment variables** — override individual values

### config.yaml

```yaml
minecraft:
  host: localhost
  rcon_port: 25575           # Optional RCON fallback
  rcon_password: ""
  player_name: AIBot

mc_api:
  host: localhost            # MCPQ plugin host (Docker: minecraft)
  port: 1789                 # MCPQ plugin gRPC port
  player_name: AIBot         # In-game player name to control

llm:
  provider: openrouter       # openai | anthropic | ollama | openrouter | opencode_server
  model: openai/gpt-4o-mini # Provider-specific model ID
  temperature: 0.7
  max_tokens: 4096

bridge:
  max_iterations: 100        # Safety limit
  cycle_delay: 1.0           # Seconds between actions
  memory_window: 20          # Recent actions to remember
  verbose: true

goals:
  default: "Explore the world and gather resources"
  max_depth: 5
```

### Key Environment Variables

| Variable | Description |
|----------|-------------|
| `MC_API_HOST` | MCPQ plugin hostname |
| `MC_API_PORT` | MCPQ plugin port (default: 1789) |
| `MC_API_PLAYER_NAME` | In-game player name |
| `LLM_PROVIDER` | One of: openai, anthropic, ollama, openrouter, opencode_server |
| `LLM_MODEL` | Model ID for the chosen provider |
| `LLM_OPENAI_API_KEY` | OpenAI API key (or `OPENAI_API_KEY`) |
| `LLM_ANTHROPIC_API_KEY` | Anthropic API key (or `ANTHROPIC_API_KEY`) |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `LLM_OPencode_SERVER_URL` | OpenCode Server URL |
| `LLM_OPencode_SERVER_API_KEY` | OpenCode Server API key |

A full list of overrides is in `.env.example`.

## How the Agent Works

### The Think-Act-Observe Loop

On every turn the agent:

1. **Observe** — queries player position, health, inventory, time of day, and surroundings via MCPQ
2. **Think** — sends full context (goal, state, recent actions, memory, last result) to the LLM, which returns a structured action decision with step-by-step reasoning
3. **Act** — executes the chosen action via MCPQ (gRPC)
4. **Record** — stores action and result in short-term memory
5. **Repeat** — until the goal is complete or `max_iterations` is reached

### Goal Decomposition

When given a high-level goal, the agent first asks the LLM to break it into concrete sub-goals:

```
Build a wooden house
├── Gather wood (break trees)
├── Craft planks and a crafting table
├── Build a 5x5 wooden floor
├── Build walls 3 blocks high
├── Add a door
└── Build a roof
```

Sub-goals are tracked in a tree structure. The agent marks each one complete (via the `done` action) before moving to the next. If the LLM returns no sub-goals, **hardcoded fallback plans** match common patterns (build, mine, farm, explore, enchant).

### Action Space

| Category | Actions |
|----------|---------|
| Movement | `move_to`, `move_forward`, `move_back`, `turn_left`, `turn_right`, `jump`, `teleport` |
| Building | `break_block`, `place_block`, `interact` |
| Inventory | `check_inventory`, `equip_item`, `craft_item`, `drop_item` |
| Combat | `attack` |
| Information | `scan`, `check_time`, `check_weather`, `check_health`, `check_position`, `list_players` |
| Communication | `chat` |
| Meta | `wait`, `done` (signal sub-goal completion) |

### Memory

- **Short-term**: Rolling window of recent actions (configurable, default 20), injected into each LLM prompt as structured text
- **Long-term**: Notable facts extracted from observations (position data, discoveries), persisted across turns

## Project Structure

```
minecraft-ai-bridge/
├── config.yaml                     # Default configuration
├── docker-compose.yml              # Paper server + bridge
├── Dockerfile                      # Bridge container image
├── pyproject.toml                  # Package metadata & dependencies
├── .env.example                    # Environment variable reference
├── scripts/
│   └── download-plugins.sh         # MCPQ plugin downloader
├── mcpq-plugins/                   # Mounted plugin directory
├── mcpq-config/                    # MCPQ plugin configuration
├── minecraft_ai_bridge/
│   ├── main.py                     # CLI entry point
│   ├── config.py                   # Pydantic config (YAML + env vars)
│   ├── minecraft/
│   │   ├── mc_api.py               # McpqClient async gRPC wrapper
│   │   ├── actions.py              # 24 action handlers + dispatcher
│   │   ├── observer.py             # World state observation
│   │   └── rcon.py                 # Async RCON client (optional fallback)
│   ├── llm/
│   │   ├── client.py               # LLM abstraction (5 providers)
│   │   ├── prompts.py              # System prompts & state formatting
│   │   └── models.py               # Pydantic data models
│   └── bridge/
│       ├── orchestrator.py         # Main agent loop
│       ├── goal_manager.py         # Goal decomposition & tracking
│       └── memory.py               # Short + long-term memory
├── docs/
│   ├── ARCHITECTURE.md             # Deep architecture dive
│   ├── SETUP.md                    # Detailed installation guide
│   ├── CLI.md                      # CLI reference
│   ├── AGENT.md                    # Agent internals
│   └── EXTENDING.md                # How to extend the bridge
├── examples/
│   └── goals.yaml                  # Example goals with sub-goals
└── AGENTS.md                       # AI handoff notes
```

## Extending

See `docs/EXTENDING.md` for detailed guides on:

- **Adding a new action** — 5 steps from enum to handler to LLM schema
- **Adding a new LLM provider** — implement the `LLMClient` ABC
- **Custom goal decompositions** — extend or replace the fallback plans
- **Custom memory strategies** — plugin different memory backends

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| `No entity was found` for player ops | Fake player not spawned | Bridge auto-spawns one on connect; check `fp spawn` succeeded in logs |
| MCPQ connection refused | Wrong host/port or MCPQ not loaded | Verify `mc_api.host`/`port`, check server logs for `mcpq` startup |
| LLM returns 401 / auth error | Missing or invalid API key | Check env vars: `LLM_OPENAI_API_KEY`, `OPENROUTER_API_KEY`, etc. |
| Client "I'm still on 1.20.1" | Client version too new for Paper server | Use Minecraft 1.20.1 client (Prism Launcher, MultiMC, or official launcher Installations tab) |
| LLM re-scans endlessly | World state unclear or player can't reach goal | Check player position; try a simpler goal; enable `--verbose` to see LLM reasoning |
| Bridge container exits immediately | MCPQ not reachable | Wait for Paper to fully start; check `docker compose logs minecraft` |

## License

MIT
