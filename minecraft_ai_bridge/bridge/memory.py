"""Agent memory — maintains short-term and limited long-term context
with optional SQLite-backed persistence across sessions.

Short-term memory keeps the last N action/observation pairs.
Long-term memory stores notable discoveries (positions, resources, etc.).

When a database path is configured, facts are persisted across agent runs.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from collections import deque
from typing import Any

from ..llm.models import MemoryEntry, Message, Role

logger = logging.getLogger(__name__)

_LOCAL = threading.local()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Return a thread-local SQLite connection."""
    attr = f"_mem_conn_{id(db_path)}"
    if not hasattr(_LOCAL, attr):
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        setattr(_LOCAL, attr, conn)
    return getattr(_LOCAL, attr)


class AgentMemory:
    """Lightweight memory for the Minecraft agent.

    The memory feeds into the LLM prompt as conversation history and
    a separate "notable facts" section.

    Persistence
    -----------
    When *db_path* is provided (or the ``AGENT_MEMORY_DB`` env var is set),
    facts are saved to a SQLite database and reloaded on the next run.
    Turn-based history is kept in-memory (not persisted across sessions),
    while long-term facts survive restarts.
    """

    def __init__(self, window: int = 20, db_path: str | None = None) -> None:
        self._window = window
        self._short_term: deque[MemoryEntry] = deque(maxlen=window)
        self._long_term: list[str] = []
        self._turn = 0
        self._db_path = db_path or os.environ.get("AGENT_MEMORY_DB", "")

        if self._db_path:
            self._init_db()
            self._load_facts_from_db()

    # ── Database initialisation ───────────────────────────────────────

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        try:
            conn = _get_connection(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_facts (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact  TEXT NOT NULL UNIQUE,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_goals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    completed   INTEGER DEFAULT 0,
                    session_id  TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        except Exception as exc:
            logger.warning("Could not initialise memory database: %s", exc)
            self._db_path = ""  # fall back to in-memory only

    def _load_facts_from_db(self) -> None:
        """Restore facts from a previous session."""
        if not self._db_path:
            return
        try:
            conn = _get_connection(self._db_path)
            rows = conn.execute(
                "SELECT fact FROM agent_facts ORDER BY id"
            ).fetchall()
            for row in rows:
                self._long_term.append(row["fact"])
            if self._long_term:
                logger.info(
                    "Restored %d fact(s) from memory database", len(self._long_term)
                )
        except Exception as exc:
            logger.debug("Could not load facts from DB: %s", exc)

    def _save_fact_to_db(self, fact: str) -> None:
        """Persist a single fact to the database."""
        if not self._db_path:
            return
        try:
            conn = _get_connection(self._db_path)
            conn.execute(
                "INSERT OR IGNORE INTO agent_facts (fact) VALUES (?)",
                (fact,),
            )
            conn.commit()
        except Exception as exc:
            logger.debug("Could not save fact to DB: %s", exc)

    def save_goal(self, description: str, completed: bool = False,
                  session_id: str | None = None) -> None:
        """Record a goal in the persistent database."""
        if not self._db_path:
            return
        try:
            conn = _get_connection(self._db_path)
            conn.execute(
                "INSERT INTO agent_goals (description, completed, session_id) "
                "VALUES (?, ?, ?)",
                (description, int(completed), session_id or ""),
            )
            conn.commit()
        except Exception as exc:
            logger.debug("Could not save goal to DB: %s", exc)

    def close(self) -> None:
        """Close the database connection if open.

        Call this during shutdown to ensure WAL checkpointing.
        """
        if self._db_path:
            try:
                attr = f"_mem_conn_{id(self._db_path)}"
                conn = _get_connection(self._db_path)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                if hasattr(_LOCAL, attr):
                    delattr(_LOCAL, attr)
            except Exception:
                pass

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
        """Record a world observation snapshot.

        Skips recording if the state is identical to the previous
        observation to avoid filling the window with noise.
        """
        from ..llm.prompts import format_state

        state_dict = {}
        if hasattr(state, "__dict__"):
            state_dict = state.__dict__
        elif isinstance(state, dict):
            state_dict = state

        # Deduplicate: skip if state hasn't changed (compare summary)
        summary = format_state(state_dict)
        if self._short_term:
            last = self._short_term[-1]
            if last.role == Role.USER and last.summary == f"--- Observation ---\n{summary}":
                logger.debug("Skipping duplicate observation")
                return

        self._turn += 1
        entry = MemoryEntry(
            turn=self._turn,
            role=Role.USER,
            summary=f"--- Observation ---\n{summary}",
            raw=str(state_dict),
        )
        self._short_term.append(entry)

    def remember_fact(self, fact: str) -> None:
        """Store an important fact in long-term memory (and DB if configured)."""
        if fact not in self._long_term:
            self._long_term.append(fact)
            self._save_fact_to_db(fact)
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

    def clear_all(self) -> None:
        """Clear short and long-term memory (both in-memory and DB)."""
        self._short_term.clear()
        self._long_term.clear()
        if self._db_path:
            try:
                conn = _get_connection(self._db_path)
                conn.execute("DELETE FROM agent_facts")
                conn.commit()
            except Exception:
                pass

    @property
    def short_term_summary(self) -> str:
        """Brief one-line-per-entry for compact context."""
        lines = []
        for e in self._short_term:
            lines.append(f"[T{e.turn}] {e.summary}")
        return "\n".join(lines[-15:])  # last 15 entries
