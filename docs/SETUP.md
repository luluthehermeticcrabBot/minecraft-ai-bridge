# Setup Guide

This guide covers all installation methods and configuration options for the Minecraft AI Bridge.

## Prerequisites

- **Python 3.11+**
- **Docker** (recommended for the Paper server) and **Docker Compose v2**
- **An LLM provider account/key** — OpenAI, Anthropic, or OpenRouter
- **~5GB free disk space** for the Paper server + world files

## Method 1: Docker (Recommended)

This starts a complete Paper 26.1.2 server with MCPQ and the built-in bot plugin, then runs the bridge.

### Step 1: Clone and Download

```bash
git clone <repo-url>
cd minecraft-ai-bridge

# Download the MCPQ plugin jar
chmod +x scripts/download-plugins.sh
./scripts/download-plugins.sh
```

### Step 2: Configure LLM

Create a `.env` file in the project root:

```bash
# For OpenRouter (recommended — broadest model selection)
OPENROUTER_API_KEY=sk-or-...

# Or for OpenAI
# OPENAI_API_KEY=sk-...

# Or for Anthropic
# ANTHROPIC_API_KEY=sk-ant-...
```

### Step 3: Configure Server Operators

The bridge agent needs operator (OP) permissions to use world-manipulation commands (`/setblock`, `/give`, etc.). The `docker-compose.yml` includes an `OPS` env var on the minecraft service that grants OP to specific usernames:

```yaml
environment:
  OPS: "AIBot,TestBot"
```

Add or remove usernames as needed for your fakeplayer configuration.

### Step 4: Start the Server

```bash
docker compose up -d minecraft
```

First startup takes 2-5 minutes (downloading Paper, initializing world). Watch logs:

```bash
docker compose logs -f minecraft
```

Wait for: `Done (XX.XXXs)! For help, type "help"`

### Step 4: Run the Bridge

```bash
GOAL="Build a house" docker compose run --rm bridge
```

To configure the LLM provider:

```bash
LLM_PROVIDER=openrouter \
LLM_MODEL=openai/gpt-4o-mini \
GOAL="Explore and find a village" \
docker compose run --rm bridge
```

### Persistent Bridge Mode

To run the bridge as a persistent service (restarts on crash):

```bash
docker compose up -d bridge
```

Set the default goal in `docker-compose.yml` or `.env`:

```bash
echo 'GOAL="Build a cobblestone bridge over the river"' >> .env
```

## Method 2: Local Installation

For development or connecting to an existing Paper server.

### Step 1: Install

```bash
git clone <repo-url>
cd minecraft-ai-bridge
pip install -e .
```

For Anthropic:
```bash
pip install -e ".[anthropic]"
```

For dev tools (testing, linting):
```bash
pip install -e ".[dev]"
```

### Step 2: Configure

```bash
cp .env.example .env
# Edit with your actual API keys and server settings

cp config.yaml config.yaml
# Edit mc_api.host/mc_api.port if your Paper server is remote
```

### Step 3: Have a Paper Server with MCPQ

You need a Paper 26.1.2 server with:
1. [MCPQ plugin](https://github.com/mcpq/mcpq-plugin) v2.2+
2. The included bot plugin (`bot-plugin/`) — provides `/botsummon <name>` for player entity creation
3. MCPQ configured to listen on `0.0.0.0:1789`

If using a local server without Docker, ensure MCPQ's `config.yml` has:

```yaml
host: 0.0.0.0
port: 1789
```

### Step 4: Run

```bash
# Basic usage
minecraft-ai-bridge "Build a house"

# Verbose logging
minecraft-ai-bridge --verbose "Mine diamond ore"

# Custom config
minecraft-ai-bridge -c my-config.yaml "Plant a wheat farm"

# Just LLM provider info
minecraft-ai-bridge --list-providers
```

## Paper Server Setup (Manual)

If not using Docker, here's how to set up the server manually.

### 1. Install Paper 26.1.2

```bash
# Download latest Paper 26.1.2 build
PAPER_BUILD=$(curl -s "https://api.papermc.io/v2/projects/paper/versions/26.1.2/builds" | python3 -c "import json,sys; print(json.load(sys.stdin)['builds'][-1]['build'])")
wget "https://api.papermc.io/v2/projects/paper/versions/26.1.2/builds/${PAPER_BUILD}/downloads/paper-26.1.2-${PAPER_BUILD}.jar" -O paper.jar

# First run to generate files
java -jar paper.jar nogui

# Accept EULA
echo "eula=true" > eula.txt
```

### 2. Download and Build Plugins

```bash
# MCPQ plugin
MCPQ_VERSION=2.2
wget https://github.com/mcpq/mcpq-plugin/releases/download/v${MCPQ_VERSION}/mcpq-${MCPQ_VERSION}.jar -P plugins/

# Build the bot plugin (provides /botsummon for player entity)
cd bot-plugin
mvn clean package -DskipTests
cp target/mc-bot-plugin-*.jar ../mcpq-plugins/
cd ..
```

### 3. Configure MCPQ

Create `plugins/mcpq/config.yml`:

```yaml
host: 0.0.0.0  # Allow external connections
port: 1789
debug: false
```

### 4. Configure Server

Edit `server.properties`:

```properties
online-mode=false          # Disable auth for local testing
spawn-protection=0         # Allow block breaking at spawn
difficulty=easy
```

### 5. Start Server

```bash
java -jar paper.jar nogui
```

The MCPQ plugin will listen on port 1789. Verify it's running:

```bash
# From the bridge machine
nc -zv <server-ip> 1789
```

## Configuration Reference

### Environment Variables (`.env`)

```bash
# ── Minecraft / MCPQ ──
MINECRAFT_HOST=localhost           # Server hostname
MINECRAFT_RCON_PORT=25575          # RCON port (optional)
MINECRAFT_RCON_PASSWORD=changeme   # RCON password (optional)

MC_API_HOST=localhost              # MCPQ plugin host
MC_API_PORT=1789                   # MCPQ plugin gRPC port
MC_API_PLAYER_NAME=AIBot           # In-game player name

# ── LLM Provider (pick one) ──
LLM_PROVIDER=openrouter            # openai | anthropic | ollama | openrouter | opencode_server
LLM_MODEL=openai/gpt-4o-mini      # Model for chosen provider
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

# OpenAI
OPENAI_API_KEY=sk-...              # OpenAI API key

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...       # Anthropic API key

# Ollama
LLM_OLLAMA_BASE_URL=http://localhost:11434

# OpenRouter
OPENROUTER_API_KEY=sk-or-...       # OpenRouter API key

# OpenCode Server
LLM_OPencode_SERVER_URL=http://localhost:4096
LLM_OPencode_SERVER_API_KEY=
LLM_OPencode_SERVER_MODEL=big-pickle

# ── Bridge Behavior ──
BRIDGE_MAX_ITERATIONS=100
BRIDGE_CYCLE_DELAY=1.0
BRIDGE_MEMORY_WINDOW=20
BRIDGE_VERBOSE=true
```

### `config.yaml` Reference

```yaml
minecraft:
  host: localhost                # Minecraft server host
  rcon_port: 25575               # RCON port (optional)
  rcon_password: ""              # RCON password (optional)
  player_name: AIBot             # Player name for RCON commands

mc_api:
  host: localhost                # MCPQ plugin host
  port: 1789                     # MCPQ plugin gRPC port
  player_name: AIBot             # Player to control

llm:
  provider: openrouter           # See LLM_PROVIDER above
  model: openai/gpt-4o-mini      # See LLM_MODEL above
  temperature: 0.7
  max_tokens: 4096

bridge:
  max_iterations: 100            # Max think-act-observe cycles
  cycle_delay: 1.0               # Seconds between actions
  memory_window: 20              # Actions kept in short-term memory
  verbose: true                  # Show LLM reasoning in logs

goals:
  default: "Explore the world and gather resources"
  max_depth: 5                   # Max sub-goal nesting level
```

Env vars override YAML values. The env var name is `{section}_{field}` uppercased (e.g., `mc_api.host` → `MC_API_HOST`).

## Docker Image Build

The bridge Docker image is built automatically by `docker compose`. To build manually:

```bash
docker build -t minecraft-ai-bridge .
```

The image uses `python:3.13-slim`, copies the package source, and installs via `pip install -e .`. The entrypoint is `minecraft-ai-bridge`.

## Verifying the Setup

### Check MCPQ is reachable

```bash
# From the bridge container or host
nc -zv <server-ip> 1789
# Should show: Connection succeeded
```

### Check the fake player is spawned

```bash
# In the server console
docker compose exec minecraft rcon-cli "list"
# Should show: There are 1 of 10 players online: AIBot
```

### Run a quick test

```bash
# Run bridge for 3 cycles with verbose logging
minecraft-ai-bridge --verbose "Say hello to the world"
```

### Check bridge logs

```bash
docker compose logs bridge
# Look for: "Player 'AIBot' already present" or "spawning fake player"
# And: "LLM decision: chat" with the actual reasoning
```

## Running Tests

The project has **182 tests** (160 unit + 22 integration):

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests (requires a running Paper server + MCPQ for integration tests)
pytest tests/

# Run only unit tests (no server needed)
pytest tests/ -k "not integration"

# Run only integration tests
pytest tests/test_integration.py -v

# Run with live logging
pytest tests/ -v --tb=short
```

Integration tests connect to a real MCPQ server and use real LLM inference (OpenRouter `openai/gpt-oss-20b`). Ensure your `.env` has a valid `OPENROUTER_API_KEY` and the Paper server is running.

Unit tests use `MockMcpqClient` — an in-memory MCPQ mock that simulates a 3D world deterministically. No server or LLM needed.
