"""In-game chat command interface.

Players can interact with the agent through prefixed commands sent in
Minecraft chat.  The agent periodically polls for recent chat messages
and dispatches recognised ``!commands``.

Supported commands
------------------
``!status``     — Report current goal, turn count, position, and health.
``!stop``       — Pause / shut down the agent gracefully.
``!goal <...>`` — Re-assign the agent's goal mid-session.
``!goto <p>``   — Teleport to a named player.
``!follow <p>`` — Follow a named player (stay within 5 blocks).
``!come``       — Teleport the speaker to the agent.
``!help``       — List available commands.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Pattern for parsing chat messages that look like command invocations.
# Matches:  "<PlayerName> !command args" or "<PlayerName> !command"
_COMMAND_RE = re.compile(r"<([^>]+)>\s+((?:/[!\u00a7]?|!)\w+)(.*)")

# Commands the handler recognises
COMMANDS = {
    "!status",
    "!stop",
    "!goal",
    "!goto",
    "!follow",
    "!come",
    "!help",
}


class ChatCommandHandler:
    """Listens for ``!commands`` in chat and routes them to the orchestrator.

    Usage::

        handler = ChatCommandHandler(orchestrator)
        # In the main loop:
        await handler.poll()
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator
        self._last_check: str | None = None

    # ── Polling ──────────────────────────────────────────────────────

    async def poll(self) -> None:
        """Check for new chat messages and process any matching commands.

        Uses MCPQ's ``ChatEvent`` polling API to catch in-game chat
        messages.  Should be called once per agent turn.
        """
        mc = getattr(self._orch, "_mc", None)
        if mc is None:
            return

        try:
            events = await mc.get_chat_events()
        except Exception:
            return

        if not events:
            return

        for event in events:
            # Each ChatEvent has .player.name and .message
            sender = getattr(event, "player", None)
            sender_name = getattr(sender, "name", "?") if sender else "?"
            message = getattr(event, "message", "")
            line = f"<{sender_name}> {message}"
            await self._process_line(line.strip())

    async def _process_line(self, line: str) -> None:
        """Parse a single chat line and dispatch any command found."""
        m = _COMMAND_RE.match(line)
        if not m:
            return

        sender = m.group(1)
        raw_cmd = m.group(2).strip().lower()
        args = m.group(3).strip()

        # Strip leading slash if present (some server formats include one)
        if raw_cmd.startswith("/"):
            raw_cmd = raw_cmd[1:]

        if raw_cmd not in COMMANDS:
            return

        logger.info("Chat command from %s: %s %s", sender, raw_cmd, args)
        await self.handle_command(raw_cmd, args, sender)

    # ── Dispatch ─────────────────────────────────────────────────────

    async def handle_command(self, command: str, args: str, sender: str) -> None:
        """Route a parsed command to the appropriate handler."""
        dispatch = {
            "!status": self._cmd_status,
            "!stop": self._cmd_stop,
            "!goal": self._cmd_goal,
            "!goto": self._cmd_goto,
            "!follow": self._cmd_follow,
            "!come": self._cmd_come,
            "!help": self._cmd_help,
        }
        handler = dispatch.get(command)
        if handler:
            await handler(args, sender)

    # ── Command handlers ─────────────────────────────────────────────

    async def _cmd_status(self, args: str, sender: str) -> None:
        """Report current agent status to the chat."""
        orch = self._orch
        lines = [
            f"@{sender} Status:",
            f'  Goal: "{getattr(orch, "_goals", None) and orch._goals.current_goal or "none"}"',
            f"  Turns: {getattr(orch, '_turn', 0)}",
        ]
        # Add position if available
        mc = getattr(orch, "_mc", None)
        if mc and mc.connected:
            try:
                pos = await mc.get_player_pos()
                if pos:
                    lines.append(f"  Position: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")
            except Exception:
                pass
        await self._send("\n".join(lines))

    async def _cmd_stop(self, args: str, sender: str) -> None:
        """Signal the agent to stop after the current turn."""
        await self._send(f"@{sender} Shutting down by request …")
        orch = self._orch
        orch._stop_requested = True  # checked in the main loop

    async def _cmd_goal(self, args: str, sender: str) -> None:
        """Re-assign the agent's goal."""
        if not args:
            await self._send(f"@{sender} Usage: !goal <description>")
            return
        orch = self._orch
        if hasattr(orch, "_goals") and hasattr(orch, "_memory"):
            orch._memory.clear_short_term()
            await orch._goals.set_goal(args)
            await self._send(
                f'@{sender} Goal re-assigned to: "{args}" ({orch._goals.sub_goal_count} sub-goals)'
            )

    async def _cmd_goto(self, args: str, sender: str) -> None:
        """Teleport to a named player."""
        if not args:
            await self._send(f"@{sender} Usage: !goto <player>")
            return
        target = args.split()[0]
        mc = getattr(self._orch, "_mc", None)
        if mc and mc.connected:
            try:
                await mc.run_as_player(f"tp @p {target}")
                await self._send(f"@{sender} Teleported to {target}")
            except Exception as exc:
                await self._send(f"@{sender} Could not teleport to {target}: {exc}")

    async def _cmd_follow(self, args: str, sender: str) -> None:
        """Toggle follow-mode for a named player."""
        if not args:
            await self._send(f"@{sender} Usage: !follow <player>")
            return
        target = args.split()[0]
        orch = self._orch
        orch._follow_target = target
        orch._memory.remember_fact(f"Following player: {target}")
        await self._send(f"@{sender} Now following {target} (stays ~4 blocks away)")

    async def _cmd_come(self, args: str, sender: str) -> None:
        """Teleport the sender to the agent's position."""
        mc = getattr(self._orch, "_mc", None)
        if mc and mc.connected:
            try:
                await mc.run_as_player(f"tp {sender} @p")
                await self._send(f"@{sender} You have been teleported to me!")
            except Exception as exc:
                await self._send(f"@{sender} Could not teleport you: {exc}")

    async def _cmd_help(self, args: str, sender: str) -> None:
        """List available commands."""
        help_text = (
            f"@{sender} Available commands: "
            "!status !stop !goal <...> !goto <player> "
            "!follow <player> !come !help"
        )
        await self._send(help_text)

    # ── Helper ───────────────────────────────────────────────────────

    async def _send(self, message: str) -> None:
        """Send a chat message via the MCPQ client."""
        mc = getattr(self._orch, "_mc", None)
        if mc and mc.connected:
            with contextlib.suppress(Exception):
                await mc.post_to_chat(message)
