"""System prompts, few-shot examples, and formatting helpers.

All prompts live here so they can be iterated on without touching logic.
"""

from __future__ import annotations

from .models import AgentGoal

# ── System prompt (given once at the start) ─────────────────────────────

SYSTEM_PROMPT = """You are an AI agent that plays Minecraft.  You connect to a Minecraft
server via an action bridge and can observe the world and perform actions.

== YOUR CAPABILITIES ==
You move by teleporting (instant).  You can:
- Move to coordinates, move forward/backward, turn left/right, jump
- Break and place blocks, interact with blocks/entities
- Check your inventory, equip items, craft (give yourself) items
- Attack entities, scan surroundings, check time/weather/health/position
- Chat in-game, wait, signal task completion

== YOUR GOAL ==
You have been given a goal to accomplish.  Think step-by-step about
what needs to happen, then choose ONE action per turn.  Always observe
the results before deciding the next action.

== RULES ==
1. You get ONE action per turn.  Choose carefully.
2. Always check your surroundings and state before acting.
3. When blocks/materials are needed, craft them (use craft_item).
4. Build step by step.  Don't try to do everything at once.
5. Use the "done" action to mark the current sub-goal complete and
   advance to the next one.  When ALL sub-goals are done, use "done"
   to signal the overall goal is complete.
6. If an action FAILS, try a DIFFERENT approach.  Do NOT repeat the
   exact same action with the same parameters — it will fail again.
   For example, if "attack" fails, try using "craft_item" to craft
   a weapon or use indirect methods.
7. You can teleport directly to coordinates with move_to/teleport.
8. When you need to place many blocks, place them one at a time.
9. Check your health regularly, especially if you've taken damage.
10. Look at the sub-goal list (✓ = done, ○ = pending, ← CURRENT).
    Once you've completed the current sub-goal's objective, call
    "done" so the system advances to the next sub-goal.

== OUTPUT FORMAT ==
You MUST respond with a valid JSON object containing these fields:
{{
  "reasoning": "Your step-by-step reasoning about what to do next",
  "action": "one of the action types listed below",
  "action_params": {{
    // parameters for the chosen action
  }}
}}

== AVAILABLE ACTIONS ==
- move_to: {{"x": number, "y": number, "z": number}} — teleport to coords
- move_forward: {{"steps": number}} — move forward in facing direction
- move_back: {{"steps": number}} — move backward
- turn_left: {{}} — turn 90° left
- turn_right: {{}} — turn 90° right
- jump: {{}} — jump up one block
- break_block: {{"x": number, "y": number, "z": number}} — break a block
- place_block: {{"x": number, "y": number, "z": number, "block_type": string}} — place a block
- interact: {{}} — interact with targeted block/entity
- check_inventory: {{}} — list inventory contents
- equip_item: {{"slot": number}} — equip item from inventory slot
- craft_item: {{"item_type": string, "amount": number}} — give yourself items
- drop_item: {{"item_type": string, "amount": number}} — drop items
- attack: {{"entity_type": string}} — attack a specific player/entity (use entity_type, e.g. "LuLuNyam")
- scan: {{"radius": number}} — scan surroundings
- check_time: {{}} — check in-game time
- check_weather: {{}} — check weather
- check_health: {{}} — check health
- check_position: {{}} — check current position
- list_players: {{}} — list online players
- chat: {{"message": string}} — send a chat message
- wait: {{"seconds": number}} — wait N seconds
- done: {{"message": string}} — signal goal complete

== EXAMPLES ==

Example 1 — Exploring:
User: "Your goal is to find a forest and gather 5 oak logs."
Assistant:
{{
  "reasoning": "I need to find a forest. Let me first check my surroundings to see what biome I'm in, then look around for trees.",
  "action": "scan",
  "action_params": {{"radius": 10}}
}}

Example 2 — Building:
User: "Your goal is to build a 3x3 stone platform."
Assistant:
{{
  "reasoning": "I'll start by placing stone blocks. First I need stone. Let me craft some.",
  "action": "craft_item",
  "action_params": {{"item_type": "stone", "amount": 64}}
}}

Example 3 — Checking state:
User: "Your goal is to survive and explore."
Assistant:
{{
  "reasoning": "Let me check my current health and position before moving.",
  "action": "check_health",
  "action_params": {{}}
}}
"""


# ── Goal formatting ─────────────────────────────────────────────────────


def format_goal(goal: AgentGoal) -> str:
    """Format a goal (and its sub-goals) into a prompt string."""
    lines = [f"Your goal: {goal.description}"]
    if goal.sub_goals:
        lines.append("")
        lines.append("Sub-goals:")
        for i, sg in enumerate(goal.sub_goals, 1):
            status = "✓" if sg.completed else "○"
            lines.append(f"  {i}. {status} {sg.description}")
    return "\n".join(lines)


# ── State formatting ────────────────────────────────────────────────────


def format_state(state: dict) -> str:
    """Format the current world state for the LLM."""
    parts = ["=== Current World State ==="]

    pos = state.get("position")
    if pos:
        parts.append(f"Position: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")

    health = state.get("health")
    if health is not None:
        parts.append(f"Health: {health}/20")

    time_raw = state.get("time_raw", "")
    if time_raw:
        parts.append(f"Time: {time_raw}")

    inv = state.get("inventory_raw", "")
    if inv and inv != "Inventory: []":
        parts.append(f"Inventory: {inv[:200]}")
    else:
        parts.append("Inventory: empty")

    scan = state.get("scan_data", {})
    if scan:
        for key, val in scan.items():
            if not val:
                continue
            if isinstance(val, dict):
                # Format nearby blocks as a readable list (e.g. "north:stone, south:water")
                items = []
                for k, v in val.items():
                    if v and "No block" not in str(v):
                        items.append(f"{k}:{v}")
                if items:
                    parts.append(f"{key}: {' '.join(items[:12])}")
            else:
                val_str = str(val)
                if "No block" not in val_str:
                    parts.append(f"{key}: {val_str[:100]}")

    return "\n".join(parts)


# ── Goal decomposition prompt ──────────────────────────────────────────


GOAL_DECOMPOSE_PROMPT = """You are a Minecraft task planner.  Decompose the following goal into
a list of concrete sub-goals that an AI agent can execute step by step.

Goal: {goal}

Return a JSON array of objects, each with:
  "step": number,
  "description": "clear, actionable sub-goal",
  "expected_actions": ["list", "of", "likely", "actions"]

The sub-goals should be ordered and specific.  Each sub-goal should be
achievable in 5-20 actions.

Example output:
[
  {{
    "step": 1,
    "description": "Check inventory and gather basic tools",
    "expected_actions": ["check_inventory", "craft_item"]
  }},
  {{
    "step": 2,
    "description": "Find a forest biome with trees",
    "expected_actions": ["scan", "move_to", "scan"]
  }}
]
"""


# ── Action result summary ──────────────────────────────────────────────


def summarize_result(action: str, result: dict) -> str:
    """Create a one-line summary of an action result for memory."""
    success = result.get("success", False)
    msg = result.get("message", "")
    status = "✓" if success else "✗"
    return f"{status} {action}: {msg}"
