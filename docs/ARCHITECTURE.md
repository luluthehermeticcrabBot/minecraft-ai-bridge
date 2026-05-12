# Architecture

This document explains the design, rationale, and data flow of the Minecraft AI Bridge.

## Design Philosophy

The bridge is built on a **three-layer architecture** with strict separation of concerns:

1. **Minecraft Interface Layer** — talks to the game server
2. **LLM Abstraction Layer** — talks to language models
3. **Bridge Orchestration Layer** — the "brain" connecting everything

Each layer is independently testable, swappable, and extensible. The layers communicate through well-defined interfaces (abstract base classes, dataclasses, and pydantic models).

## Layer 1: Minecraft Interface

**Package**: `minecraft_ai_bridge.minecraft`  
**Entry points**: `McpqClient`, `execute_action()`, `Observer`

### McpqClient (`mc_api.py`)

An async wrapper around the MCPQ plugin's gRPC API. MCPQ (Minecraft Protobuf Queries) is a Paper plugin that exposes a gRPC interface for reading and writing world state and controlling players — no game client needed.

```python
client = McpqClient(host="localhost", port=1789, player_name="AIBot")
await client.connect()

# Direct world manipulation
await client.set_block("stone", 10, 64, 20)
block = await client.get_block(10, 64, 20)

# Player control
pos = await client.get_player_pos()
await client.teleport_player(10.0, 65.0, 20.0)

# Commands
result = await client.run_command_blocking("give @p diamond 1")
await client.post_to_chat("Hello from AI!")

# Discovery
players = await client.get_players_online()
time = await client.get_time()

await client.disconnect()
```

All gRPC calls are dispatched via `asyncio.to_thread()` to avoid blocking the event loop, since the generated gRPC stubs are synchronous.

### Action Handlers (`actions.py`)

24 atomic actions the LLM can invoke, organized by category:

- **Movement**: `move_to`, `move_forward`, `move_back`, `turn_left`, `turn_right`, `jump`, `teleport`
- **Interaction**: `break_block`, `place_block`, `interact`
- **Inventory**: `check_inventory`, `equip_item`, `craft_item`, `drop_item`
- **Combat**: `attack`
- **Information**: `scan`, `check_time`, `check_weather`, `check_health`, `check_position`, `list_players`
- **Communication**: `chat`
- **Meta**: `wait`, `done`

Each handler is an `async` function taking `(McpqClient, params: dict) -> ActionResult`:

```python
async def _place_block(mc: McpqClient, params: dict) -> ActionResult:
    x = params.get("x")
    y = params.get("y")
    z = params.get("z")
    block_type = params.get("block_type", "stone")
    await mc.set_block(block_type, int(x), int(y), int(z))
    return ActionResult(
        success=True,
        action=ActionType.PLACE_BLOCK,
        message=f"Placed {block_type} at ({x}, {y}, {z})",
    )
```

The `_HANDLERS` dict maps `ActionType` enum values to handler functions — simple dispatch, no reflection.

### Observer (`observer.py`)

Gathers world state on each turn:

```python
class WorldState:
    position: tuple[float, float, float] | None
    health: float
    inventory: str         # raw NBT data string
    time: str               # game time string
    players: list[str]
    scan_data: dict         # nearby blocks, cardinal samples
    raw_command_outputs: dict  # all raw responses for debugging
```

The observer uses `asyncio.gather()` to query position, inventory, health, time, and players concurrently, then parses command outputs where useful.

### RCON Client (`rcon.py`, optional fallback)

An async RCON client is included as a fallback for admin commands, but MCPQ replaces all gameplay functionality. The RCON implementation uses a custom `asyncio`-compatible read loop to avoid hangs on Python 3.13+.

## Layer 2: LLM Abstraction

**Package**: `minecraft_ai_bridge.llm`  
**Entry point**: `create_llm_client(AppConfig)`

### LLMClient Protocol (`client.py`)

Abstract base class with a single method:

```python
class LLMClient(ABC):
    @abstractmethod
    async def decide(
        self,
        system_prompt: str,
        messages: list[Message],
    ) -> LLMResponse:
        ...
```

`LLMResponse` contains the action name, params dict, and reasoning:

```python
class LLMResponse(BaseModel):
    action: str
    action_params: dict[str, Any]
    reasoning: str
```

### Five Provider Implementations

| Provider | Class | Backend SDK | Features |
|----------|-------|-------------|----------|
| **OpenAI** | `OpenAIClient` | `openai` library | Tool calling, streaming support |
| **Anthropic** | `AnthropicClient` | `anthropic` library | Tool calling via `anthropic.types.ToolUseBlock` |
| **Ollama** | `OllamaClient` | `httpx` HTTP calls | OpenAI-compatible chat endpoint, tool calling |
| **OpenRouter** | `OpenRouterClient` | `openai` library (custom base_url) | Same as OpenAI, extra headers for referer/title |
| **OpenCode Server** | `OpenCodeServerClient` | `httpx` HTTP calls | Session-based API: POST /sessions, then POST /session/{id}/message |

### System Prompts (`prompts.py`)

The agent receives a detailed system prompt that explains:
- Its role as an AI playing Minecraft
- All available actions with descriptions and parameter schemas
- The JSON output format for tool calls
- Rules of conduct (prefer scanning before moving, don't spam, etc.)

State is formatted in `format_state()` — a human-readable summary of position, health, inventory, time, and surrounding blocks.

### Action Tool Schema

The LLM is given an `ACTION_TOOL` definition in `client.py` that describes each action as a JSON Schema function call. This is the mechanism that lets structured action decisions work across all providers:

```python
ACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "act",
        "description": "Choose the next action to perform.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [a.value for a in ActionType],
                    "description": "..."
                },
                "action_params": { ... },
                "reasoning": {
                    "type": "string",
                    "description": "..."
                }
            },
            "required": ["action", "action_params", "reasoning"]
        }
    }
}
```

## Layer 3: Bridge Orchestration

**Package**: `minecraft_ai_bridge.bridge`  
**Entry point**: `Orchestrator`

### Orchestrator (`orchestrator.py`)

The main agent loop. On construction it creates LLM client, MCPQ client, observer, memory, and goal manager. The `run()` method:

1. **Connects** to MCPQ, spawns a fake player if needed, teleports to safe coordinates
2. **Decomposes** the goal into sub-goals via the LLM (with fallback plans)
3. **Loops** through think-act-observe until the goal is complete

Each step:

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Observe  │───→│  Think   │───→│   Act    │
│ (MCPQ)   │    │ (LLM)    │    │ (MCPQ)   │
└──────────┘    └──────────┘    └──────────┘
     │               │               │
     │               │               │
     ▼               ▼               ▼
┌──────────────────────────────────────────┐
│              Record (Memory)              │
└──────────────────────────────────────────┘
```

### Goal Manager (`goal_manager.py`)

Manages a tree of goals and sub-goals:

```python
class GoalNode:
    description: str
    completed: bool
    sub_goals: list[GoalNode]
```

- **Goal decomposition**: Sends the high-level goal to the LLM with instructions to return a JSON array of sub-goals
- **Fallback plans**: If the LLM fails or returns nothing, matches the goal text against patterns — "build" → 11-step construction plan, "mine" → 12-step mining plan, "farm" → 10-step farming plan, "enchant"/"workshop" → 9-step workshop plan, "explore"/"scout" → 8-step exploration plan, plus a generic 6-step fallback
- **Progress tracking**: `is_complete` property, `mark_current_complete()` method, tree traversal for next uncompleted goal

### Memory (`memory.py`)

Two-tier memory system:

```python
class AgentMemory:
    def __init__(self, window: int = 20):
        self._actions: deque[ActionRecord]  # short-term, rolling window
        self._facts: set[str]              # long-term, notable discoveries
        self._observations: deque[ObservationRecord]
```

- **Short-term**: A `deque` of recent `ActionRecord` objects (action name, success, message, timestamp). Injected into every LLM prompt as a structured text block.
- **Long-term**: A `set` of fact strings extracted from position data, discoveries, and other notable events. Persists across the entire session.
- **Summaries**: `short_term_summary` property formats recent actions for prompts, `notable_facts()` returns all long-term facts.

## Data Flow Diagram

```
User CLI ("Build a house")
    │
    ▼
Orchestrator.run()
    │
    ├── config.yaml + env vars ──→ AppConfig
    │
    ├── create_llm_client(config) ──→ LLMClient (OpenAI/Anthropic/...)
    │
    ├── McpqClient.connect() ──→ Paper Server (gRPC / MCPQ plugin)
    │
    ├── Observer(client) ──→ reads world state
    │
    ├── GoalManager.set_goal("Build a house")
    │       │
    │       ├── LLM: decompose ──→ ["Gather wood", "Craft planks", ...]
    │       └── fallback: match patterns
    │
    └── Loop (max_iterations):
            │
            ├── Observer.observe() ──→ WorldState
            │
            ├── Build context (goal + state + memory + last result)
            │
            ├── LLM.decide(system_prompt, context) ──→ LLMResponse
            │       │
            │       └── { action: "place_block", params: {...}, reasoning: "..." }
            │
            ├── execute_action(mc, action, params) ──→ ActionResult
            │
            ├── memory.record_action(action, result)
            │
            └── if action == "done" → mark sub-goal complete
                                    → if all done → exit loop
```

## Key Design Decisions

### Why MCPQ instead of RCON?

RCON is text-based and limited to running commands and reading string output. MCPQ provides:
- **Direct block manipulation**: `setBlock(x, y, z, type)`, `getBlock(x, y, z)`
- **Player entity control**: `getPlayer()`, `teleportPlayer()`, `getPlayerPos()`
- **Structured data**: Protobuf instead of parsing command output
- **No client needed**: The plugin runs server-side

### Why fakeplayer + MCPQ (not a full bot)?

MCPQ needs a `ServerPlayer` entity to control. The `tanyaofei/minecraft-fakeplayer` plugin creates a lightweight fake player entity that exists server-side only — no game client connection needed. This is more reliable and simpler than maintaining a full client bot (like pyCraft).

### Why asyncio?

The bridge spends most of its time waiting — for LLM API responses, for MCPQ gRPC calls, for rate-limit delays. asyncio allows concurrent observation queries (`asyncio.gather`) and clean timeouts without threads.

### Why pydantic-settings for config?

All configuration is merged from YAML + environment variables with proper type coercion (string "1789" → int 1789). The `from_yaml()` class method loads YAML then re-creates pydantic models with env var overrides applied, ensuring types are correct even when values come from string env vars.
