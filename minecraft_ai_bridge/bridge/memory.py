"""Agent memory — maintains short-term and limited long-term context.

Short-term memory keeps the last N action/observation pairs.
Long-term memory stores notable discoveries (positions, resources, etc.).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from ..llm.models import MemoryEntry, Message, Role

logger = logging.getLogger(__name__)


class AgentMemory:
    """Lightweight memory for the Minecraft agent.

    The memory feeds into the LLM prompt as conversation history and
    a separate "notable facts" section.
    """

    def __init__(self, window: int = 20) -> None:
        self._window = window
        self._short_term: deque[MemoryEntry] = deque(maxlen=window)
        self._long_term: list[str] = []
        self._turn = 0

    # ── Recording ────────────────────────────────────────────────────

    def record_action(self, action: str, result: dict[str, Any]) -> None:
        """Record an action and its result in short-term memory."""
        from ..llm.prompts import summarize_result

        summary = summarize_result(action, result)
        self._turn += 1
        entry = MemoryEntry(
            turn=self._turn,
            role=Role.ASSISTANT,
            summary=summary,
            raw=f"Action: {action} | Result: {result.get('message', '')}",
        )
        self._short_term.append(entry)

    def record_observation(self, state: Any) -> None:
        """Record a world observation snapshot."""
        from ..llm.prompts import format_state

        state_dict = {}
        if hasattr(state, "__dict__"):
            state_dict = state.__dict__
        elif isinstance(state, dict):
            state_dict = state

        summary = format_state(state_dict)
        self._turn += 1
        entry = MemoryEntry(
            turn=self._turn,
            role=Role.USER,
            summary=f"--- Observation ---\n{summary}",
            raw=str(state_dict),
        )
        self._short_term.append(entry)

    def remember_fact(self, fact: str) -> None:
        """Store an important fact in long-term memory."""
        if fact not in self._long_term:
            self._long_term.append(fact)
            logger.debug("Remembered: %s", fact)

    # ── Retrieval ────────────────────────────────────────────────────

    def recent_messages(self, n: int | None = None) -> list[Message]:
        """Get recent entries as LLM conversation messages."""
        n = n or self._window
        entries = list(self._short_term)[-n:]
        return [
            Message(role=e.role, content=e.summary) for e in entries
        ]

    def notable_facts(self) -> str:
        """Format long-term memory into a string for the prompt."""
        if not self._long_term:
            return ""
        return "Notable facts:\n" + "\n".join(
            f"- {fact}" for fact in self._long_term[-10:]
        )

    def turn_count(self) -> int:
        return self._turn

    def clear_short_term(self) -> None:
        self._short_term.clear()

    @property
    def short_term_summary(self) -> str:
        """Brief one-line-per-entry for compact context."""
        lines = []
        for e in self._short_term:
            lines.append(f"[T{e.turn}] {e.summary}")
        return "\n".join(lines[-15:])  # last 15 entries
