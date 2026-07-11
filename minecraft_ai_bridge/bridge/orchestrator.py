"""The bridge orchestrator — ties LLM, Minecraft, goals, and memory together
into a continuous think–act–observe loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass

from ..config import AppConfig
from ..llm.client import LLMClient, OpenCodeServerClient, create_llm_client
from ..llm.models import LLMResponse, Message, Role
from ..llm.prompts import SYSTEM_PROMPT, format_state
from ..minecraft import ActionResult, ActionType, McpqClient, Observer, WorldState, execute_action
from .chat_commands import ChatCommandHandler
from .goal_manager import GoalManager
from .inventory_manager import InventoryManager
from .memory import AgentMemory

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Full context available to the LLM on each decision turn."""

    goal: str = ""
    current_task: str = ""
    state: str = ""
    memory: str = ""
    notable_facts: str = ""
    last_action_result: str = ""
    turn: int = 0


class Orchestrator:
    """Main agent loop.

    Usage::

        config = AppConfig.from_yaml("config.yaml")
        orch = Orchestrator(config)
        await orch.run("Build a house")
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._llm: LLMClient = create_llm_client(config)
        self._mc: McpqClient | None = None
        self._observer: Observer | None = None
        self._memory = AgentMemory(window=config.bridge.memory_window)
        self._goals = GoalManager(
            llm_client=self._llm,
            max_depth=config.goals.max_depth,
        )
        self._last_result: ActionResult | None = None
        self._turn = 0
        self._verbose = config.bridge.verbose
        self._max_iterations = config.bridge.max_iterations
        self._consecutive_failures = 0
        self._max_failures = 5

        # Chat command interface (N4)
        self._cmd_handler: ChatCommandHandler | None = None
        self._stop_requested = False
        self._follow_target: str | None = None

        # Inventory manager (N1)
        self._inventory: InventoryManager | None = None

    # ── Public API ───────────────────────────────────────────────────

    async def run(self, goal: str | None = None) -> None:
        """Run the full agent loop until the goal is complete or
        ``max_iterations`` is reached."""
        goal_text = goal or self._config.goals.default
        logger.info("╔══ Starting AI Agent ══╗")
        logger.info("║ Goal: %s", goal_text)
        logger.info("║ LLM:  %s / %s", self._config.llm.provider, self._config.llm.model)
        logger.info("╚════════════════════════╝")

        # 1. Connect to Minecraft via MCPQ
        api_cfg = self._config.mc_api
        logger.info(
            "Connecting to MCPQ plugin at %s:%s ...",
            api_cfg.host,
            api_cfg.port,
        )
        await self._connect()
        logger.info("MCPQ connected — controlling player: %s", api_cfg.player_name)

        # 2. Set up goal hierarchy
        logger.info("Decomposing goal into sub-tasks via LLM ...")
        await self._goals.set_goal(goal_text)
        logger.info("Goal decomposition complete — %d sub-goals", self._goals.sub_goal_count)

        # 3. Main loop
        done = False
        while not done and self._turn < self._max_iterations:
            self._turn += 1
            try:
                done = await self._step()
            except Exception as exc:
                self._consecutive_failures += 1
                logger.exception(
                    "Fatal error on turn %d (consecutive failures: %d)",
                    self._turn,
                    self._consecutive_failures,
                )
                await self._chat(
                    f"Error on turn {self._turn}: {exc}. "
                    f"Consecutive failures: {self._consecutive_failures}"
                )

                # Backoff sleep after unexpected crashes
                await asyncio.sleep(min(5 * self._consecutive_failures, 30))

            # Check for graceful shutdown on consecutive failures
            if self._stop_requested or self._consecutive_failures >= self._max_failures:
                if self._stop_requested:
                    logger.info("Stop requested via in-game command.")
                    await self._chat("Shutting down as requested.")
                else:
                    logger.error(
                        "Too many consecutive failures (%d). Shutting down.",
                        self._consecutive_failures,
                    )
                    await self._chat(
                        f"Too many errors ({self._consecutive_failures}). Shutting down."
                    )
                break

        logger.info(
            "Agent finished after %d turns. Goal complete: %s",
            self._turn,
            self._goals.is_complete,
        )
        await self._disconnect()

    # ── Core step ────────────────────────────────────────────────────

    async def _step(self) -> bool:
        """One iteration of the think–act–observe loop.

        Returns True if the agent should stop.
        """
        logger.info("─── Turn %d ───", self._turn)

        # ── Check for in-game commands (N4) ──────────────────────
        if self._cmd_handler:
            with contextlib.suppress(Exception):
                await self._cmd_handler.poll()
        if self._stop_requested:
            return True

        # ── Follow-mode support (N4) ─────────────────────────────
        if self._follow_target:
            try:
                my_pos = await self._mc.get_player_pos()
                if my_pos is None:
                    pass
                else:
                    target_pos_raw = await self._mc.run_command_blocking(
                        f"data get entity {self._follow_target} Pos"
                    )
                    if target_pos_raw:
                        import re as _re

                        m = _re.search(r"\[([^\]]+)\]", target_pos_raw)
                        if m:
                            parts = m.group(1).split(",")
                            if len(parts) >= 3:
                                tx = float(parts[0].strip().rstrip("dD"))
                                tz = float(parts[2].strip().rstrip("dD"))
                                dx = tx - my_pos[0]
                                dz = tz - my_pos[2]
                                dist = (dx * dx + dz * dz) ** 0.5
                                if dist > 4.0:
                                    await self._mc.run_as_player(
                                        f"execute as {self._follow_target} at @s "
                                        f"run tp @p ^-3 ^ ^-3"
                                    )
            except Exception:
                pass

        # ── Periodic inventory refresh (N1) ──────────────────────
        if self._inventory and self._turn % 5 == 0:
            with contextlib.suppress(Exception):
                await self._inventory.refresh()

        # ── Observe ──────────────────────────────────────────────
        world = await self._observe()

        # ── Build context for LLM ─────────────────────────────────
        context = self._build_context(world)
        if self._verbose:
            self._log_context(context)

        # ── Think (LLM decides) ───────────────────────────────────
        # Build message list: goal + state + explicit last-result hint
        messages: list[Message] = [
            Message(role=Role.USER, content=context.goal),
            Message(role=Role.USER, content=context.state),
        ]

        # Include the last action result explicitly so the LLM can see
        # what happened (especially failures).
        if context.last_action_result:
            messages.append(
                Message(
                    role=Role.USER, content=f"=== Last Action ===\n{context.last_action_result}"
                )
            )

        # Append recent history (capped to avoid unbounded growth)
        messages.extend(self._memory.recent_messages(10))

        response = await self._llm.decide(
            system_prompt=SYSTEM_PROMPT,
            messages=messages,
        )

        if self._verbose:
            logger.info(
                "LLM decision: %s → %s", response.action, json.dumps(response.action_params)
            )

        # ── Act ───────────────────────────────────────────────────
        result = await self._act(response)

        # Track consecutive failures — count both action failures and exceptions
        if result.success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        # ── Record ────────────────────────────────────────────────
        self._memory.record_action(
            response.action,
            {
                "success": result.success,
                "message": result.message,
                "data": result.data,
            },
        )

        if self._verbose:
            logger.info("Result: %s — %s", "✓" if result.success else "✗", result.message)

        # ── Check termination ─────────────────────────────────────
        if response.action == "done" and result.success:
            self._goals.mark_current_complete()
            if self._goals.is_complete:
                return True
            # Check if there's a next sub-goal
            if self._goals.current_goal:
                await self._chat(f"Starting next task: {self._goals.current_goal}")
                return False

        return self._turn >= self._max_iterations

    # ── Sub-routines ────────────────────────────────────────────────

    async def _observe(self) -> WorldState:
        """Gather world state and record it in memory."""
        assert self._observer is not None
        state = await self._observer.observe()
        self._memory.record_observation(state)
        return state

    def _build_context(self, world: WorldState) -> AgentContext:
        """Build structured context for the LLM prompt."""
        state_dict = world.__dict__ if hasattr(world, "__dict__") else {}
        state_str = format_state(state_dict)

        # Goal context
        goal_context = (
            f"=== Goal ===\n{self._goals.progress}\n\nCurrent task: {self._goals.current_goal}"
        )

        # Memory context
        memory_str = self._memory.short_term_summary
        if not memory_str.strip():
            memory_str = "(no recent actions)"

        facts = self._memory.notable_facts()

        # Last action result
        last_result = ""
        if self._last_result:
            last_result = (
                f"Last action: {self._last_result.action.value}\n"
                f"Success: {self._last_result.success}\n"
                f"Message: {self._last_result.message}"
            )

        return AgentContext(
            goal=goal_context,
            current_task=self._goals.current_goal,
            state=f"=== World State ===\n{state_str}",
            memory=f"=== Recent Actions ===\n{memory_str}",
            notable_facts=facts,
            last_action_result=last_result,
            turn=self._turn,
        )

    async def _act(self, response: LLMResponse) -> ActionResult:
        """Execute the LLM's chosen action via the MCPQ plugin."""
        assert self._mc is not None

        try:
            action_type = ActionType(response.action)
        except ValueError:
            logger.warning("Unknown action: %s", response.action)
            return ActionResult(
                success=False,
                action=ActionType.WAIT,
                message=f"Unknown action: {response.action}",
            )

        result = await execute_action(
            self._mc,
            action_type,
            response.action_params,
        )

        self._last_result = result

        # Record important discoveries
        if action_type == ActionType.CHECK_POSITION and result.success:
            pos = result.data.get("position_raw", "")
            if pos:
                self._memory.remember_fact(f"Position data: {pos}")

        # Rate-limit delay
        await asyncio.sleep(self._config.bridge.cycle_delay)

        return result

    async def _chat(self, message: str) -> None:
        """Send a chat message as the agent."""
        if self._mc and self._mc.connected:
            with contextlib.suppress(Exception):
                await self._mc.post_to_chat(message)

    # ── Connection management ────────────────────────────────────────

    async def _connect(self) -> None:
        """Connect to the Minecraft server via the MCPQ plugin."""
        api_cfg = self._config.mc_api
        self._mc = McpqClient(
            host=api_cfg.host,
            port=api_cfg.port,
            player_name=api_cfg.player_name,
        )
        await self._mc.connect()
        self._observer = Observer(self._mc)
        logger.info("Connected to MCPQ — player name: %s", api_cfg.player_name)

        # ── Ensure a fake player entity exists ────────────────────────
        # The MCPQ-Bot Paper plugin (/botsummon) creates a ServerPlayer
        # that MCPQ can detect and control. Without this, player-relative
        # selectors like @p and MCPQ's getPlayers won't work.
        player_name = api_cfg.player_name
        logger.info("Checking if player '%s' exists …", player_name)

        try:
            # Try getting the player's position — if it works, they exist
            pos = await self._mc.get_player_pos()
            if pos is not None:
                logger.info("Player '%s' already present at %s", player_name, pos)
            else:
                raise ValueError("pos is None")
        except Exception:
            # Player doesn't exist yet — spawn via /botsummon
            logger.info("Player '%s' not found — summoning bot …", player_name)
            try:
                spawn_result = await self._mc.run_command_blocking(f"botsummon {player_name}")
                logger.info("Bot summon command: %s", spawn_result or "OK")
            except Exception as spawn_err:
                logger.warning(
                    "Failed to summon bot via /botsummon: %s  "
                    "Continuing anyway — some MCPQ ops will fail "
                    "without a player entity.",
                    spawn_err,
                )

            # Poll until the player entity is confirmed present
            logger.info("Waiting for player '%s' to be registered …", player_name)
            for _poll_attempt in range(10):
                await asyncio.sleep(1)
                try:
                    pos = await self._mc.get_player_pos()
                    if pos is not None:
                        logger.info("Player '%s' confirmed at %s", player_name, pos)
                        break
                except Exception:
                    pass
            else:
                logger.warning(
                    "Player '%s' not confirmed after polling. Continuing — some MCPQ ops may fail.",
                    player_name,
                )

        # ── Teleport to a safe location ─────────────────────────────
        # The fake player often spawns underwater or in unsafe terrain.
        # We teleport to a high Y (above any terrain) and build a solid
        # platform underneath so the bot stands on dry land.
        safe_x, safe_y, safe_z = 0, 65, 0
        logger.info(
            "Teleporting player '%s' to (%d, %d, %d) …",
            player_name,
            safe_x,
            safe_y,
            safe_z,
        )
        for attempt in range(3):
            try:
                await self._mc.teleport_player(float(safe_x), float(safe_y), float(safe_z))
                # Build a 3×3 solid platform under the player
                for dx in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        with contextlib.suppress(Exception):
                            await self._mc.set_block(
                                "dirt",
                                safe_x + dx,
                                safe_y - 1,
                                safe_z + dz,
                            )
                await asyncio.sleep(2)
                safe_pos = await self._mc.get_player_pos()
                if safe_pos:
                    logger.info(
                        "Player at (%.1f, %.1f, %.1f) — feet: %s",
                        *safe_pos,
                        await self._mc.get_block(
                            int(safe_pos[0]),
                            int(safe_pos[1]) - 1,
                            int(safe_pos[2]),
                        ),
                    )
                    break
                logger.warning("Teleport attempt %d: position unknown", attempt + 1)
            except Exception as safe_err:
                logger.warning("Safe teleport attempt %d failed: %s", attempt + 1, safe_err)
                await asyncio.sleep(2)

        # Initialise sub-systems (N1 inventory, N4 chat commands)
        self._inventory = InventoryManager(self._mc)
        try:
            await self._inventory.refresh()
            logger.info("Initial inventory: %s", self._inventory.summary)
        except Exception:
            logger.debug("Initial inventory refresh failed (expected if player just spawned)")

        self._cmd_handler = ChatCommandHandler(self)

        # Persist the goal in memory database (N3)
        root_desc = self._goals.root_description
        self._memory.save_goal(root_desc if root_desc else "Unknown goal")

        # Greet
        await self._chat("AI Agent online and ready!")

    async def _disconnect(self) -> None:
        """Clean up the MCPQ connection, memory database, and other resources."""
        if self._mc:
            await self._chat("AI Agent signing off.")
            await self._mc.disconnect()

        # Persist memory database (N3)
        if hasattr(self._memory, "close"):
            with contextlib.suppress(Exception):
                self._memory.close()

        # Clean up OpenCodeServerClient HTTP session if applicable
        if isinstance(self._llm, OpenCodeServerClient):
            with contextlib.suppress(Exception):
                await self._llm.close()

    # ── Logging ──────────────────────────────────────────────────────

    def _log_context(self, ctx: AgentContext) -> None:
        """Pretty-print context in verbose mode."""
        border = "─" * 60
        logger.debug(
            "\n%s\n[TURN %d]\n%s\n%s\n%s\n%s\n%s\n%s",
            border,
            ctx.turn,
            ctx.goal,
            ctx.state,
            ctx.memory,
            ctx.notable_facts,
            ctx.last_action_result,
            border,
        )
