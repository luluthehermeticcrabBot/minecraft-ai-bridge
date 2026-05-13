# OpenCode & Hermes Agent Skill Integration

> Status: Exploratory (P4)  
> Not a dependency — our own implementations take priority

## Concept

OpenCode and Hermes Agent provide built-in capabilities that could complement the Minecraft AI Bridge:

- **LLM inference** — The agent's configured model via OpenCode's `opencode serve`
- **Plugin system** — OpenCode plugins for web search, memory, etc.
- **Skills** — Pre-built skills for research, planning
- **Memory/context management** — Built into the agent runtime
- **Web search** — Configured search API for researching Minecraft strategies

## Option 1: OpenCode SKILL for Minecraft Bridge

An OpenCode skill that wraps the bridge's Python API:

```yaml
# .opencode/skills/minecraft-ai/skill.yaml
name: minecraft-ai
description: Control a Minecraft AI agent
tools:
  - minecraft_ai_bridge/minecraft/actions.py  # expose ActionType handlers
  - minecraft_ai_bridge/llm/prompts.py        # expose prompt templates
```

The skill would:
1. Create an `Orchestrator` instance
2. Accept user goals via OpenCode's chat interface
3. Route decisions through OpenCode's configured LLM
4. Use OpenCode's memory system for long-term context
5. Use OpenCode's web search for researching crafting recipes, strategies

### Pros
- Leverages OpenCode's existing model configuration
- Built-in memory + search without implementing from scratch
- Can use OpenCode plugins for additional capabilities

### Cons
- Ties bridge to OpenCode runtime
- OpenCode's agent loop is designed for chat/coding, not Minecraft gameplay
- May conflict with the bridge's own think-act-observe loop
- Latency from double-routing (bridge → OpenCode → LLM → OpenCode → bridge)

## Option 2: Hermes Agent Integration

Similar concept but using Hermes Agent's API:
- Hermes provides structured action spaces
- Could map Minecraft actions to Hermes tools
- Hermes handles planning/reasoning

### Hermes Agent Specifics

Hermes Agent (based on Nous Research's Hermes models) is designed as a
general-purpose agent framework with:
- **Tool calling** — structured action definitions matching our `ACTION_TOOL` schema
- **Multi-turn planning** — maintains a plan across turns, could map to goal decomposition
- **Memory management** — built-in context window management
- **Web search** — native search capabilities if configured

#### Integration Path

```
Bridge (current)           Hermes Sidecar (future)
───────────────            ─────────────────────
Orchestrator._step()  →    Hermes agent loop controls decisions
LLM.decide()          →    Hermes tool selection
execute_action()      →    Hermes executes via same handlers
```

**Key difference from OpenCode:** Hermes Agent is purpose-built for
agentic loops (tool use, planning, memory), while OpenCode is designed
for code generation and iterative coding. For a Minecraft agent, Hermes'
action-space abstraction is a better conceptual match.

**Open questions:**
1. Can Hermes Agent run as a long-lived process (hours/days)?
2. Does Hermes Agent's planning handle hierarchical goals (decomposition)?
3. Can Hermes Agent stream observations back to the bridge for action
   execution, or does it fully own the loop?
4. What's the latency of routing through Hermes vs direct LLM call?

### Decision: Skills as Optional Enhancements Only

Both OpenCode and Hermes Agent skills are **purely optional sidecars**.
The bridge must always work standalone with any supported LLM provider.
Skills can accelerate development of specific features (web search,
memory, research) but our own implementations take priority across all
feature areas.

## Option 3: Web Search Enhancement

Bridge-local implementation using OpenCode's web search:
- When the agent encounters an unknown recipe/mechanic → trigger web search
- Parse results for crafting recipes, block IDs, strategies
- Feed results into LLM context as "researched knowledge"

## Decision: OpenCode Skill as Sidecar Only

**We are NOT relying on OpenCode or Hermes Agent for core functionality.**

The bridge must work standalone with any supported LLM provider. OpenCode/Hermes integration is a **sidecar option** that:
- Provides an alternative deployment mode
- Adds web search as a bridge capability (via OpenCode's search API)
- Could accelerate development of specific features (memory, research)

Our own implementations of all features must take priority.

## Current Integration Status (2026-05-13)

The bridge already supports OpenCode as an LLM provider via `OpenCodeServerClient`
(see `minecraft_ai_bridge/llm/client.py`). This client:
- Creates sessions via `POST /sessions`
- Sends messages via `POST /session/{id}/message`
- Extracts tool-call arguments for action dispatch
- Supports multiple models per session

Recent improvements:
- ✅ `close()` actually tears down the HTTP client now (fixed B5/B6)
- ✅ Session re-creation on error (retry logic added)
- ✅ Clean async resource management

## Implementation Sketch

```
Standalone bridge:
  Orchestrator → LLM (any provider) → MCPQ → Minecraft
  Memory: in-memory deques + optional SQLite (N3)
  
OpenCode sidecar:
  OpenCode Session → Orchestrator (via OpenCodeServerClient) → MCPQ → Minecraft
                      ↑
              OpenCode skills (web search, memory, etc.)
                      ↑
              OpenCode's own memory/context management
```

The bridge already supports this via the `opencode_server` LLM provider. To make it more useful:
1. Create an OpenCode skill that wraps key bridge actions as OpenCode tools
2. Enable the bridge agent to use OpenCode's web search API for researching
   Minecraft strategies, recipes, and mechanics
3. Map OpenCode's built-in memory system to the bridge's `AgentMemory` for
   richer cross-session persistence
4. Document how to run the bridge through OpenCode

## OpenCode Usage for the Bridge

### As an LLM Provider (Current)
```
LLM_PROVIDER=opencode_server
OPENCODE_SERVER_URL=http://localhost:4096
OPENCODE_SERVER_MODEL=big-pickle
```
The bridge connects to an OpenCode server instance and uses its configured
model for action decisions and goal decomposition.

### As a Research Tool (Planned)
The bridge could call OpenCode's web search API (if available) to:
- Look up crafting recipes the agent doesn't know
- Research biome properties
- Find the nearest structure coordinates
- Get strategy advice for specific challenges

This would be implemented as a new action type (`RESEARCH`) that:
1. Sends a query to the configured search API
2. Parses the result into a structured summary
3. Feeds it into the agent's context as a "researched fact"

### As a Sidecar Skill (Future)
A full OpenCode skill (`minecraft-ai`) would:
1. Expose the bridge's action handlers as OpenCode tools
2. Let OpenCode's agent loop (not the bridge's) decide actions
3. Route Minecraft observations back through OpenCode's context

This is a **future experiment** — the bridge's own loop is more specialized.

## Key Principle
> The bridge must work standalone with any supported LLM provider.
> OpenCode/Hermes integration is a **sidecar option** only.
> Our own implementations of all features take priority.

## Open Questions

1. Does OpenCode support long-running background processes (the bridge runs for hours)?
2. Can OpenCode skills expose streaming actions (observe → decide → act loop)?
3. What's the latency overhead of routing through OpenCode vs direct LLM call?
4. Does Hermes Agent's action space mapping handle the 24-minecraft-action surface?
5. Can OpenCode's memory system be bridged to the SQLite-backed AgentMemory (N3)?
6. What's the web search API surface (rate limits, cost, supported engines)?

## References

- OpenCode SKILL format documentation
- Hermes Agent tool definition format
- `minecraft_ai_bridge/llm/client.py` — OpenCodeServerClient implementation (already exists!)
