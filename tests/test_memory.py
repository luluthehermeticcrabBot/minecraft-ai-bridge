"""Tests for AgentMemory — short-term, long-term, deduplication, persistence."""

from __future__ import annotations

import os
import tempfile

import pytest

from minecraft_ai_bridge.bridge.memory import AgentMemory
from minecraft_ai_bridge.llm.models import Role


class TestShortTermMemory:
    """Rolling window tests."""

    def test_record_action(self):
        mem = AgentMemory(window=5)
        mem.record_action("move_forward", {"success": True, "message": "Moved"})
        assert len(mem._short_term) == 1

    def test_record_observation(self):
        mem = AgentMemory(window=5)
        state = type("S", (), {"__dict__": {"position": (0, 65, 0), "health": 20.0}})()
        mem.record_observation(state)
        assert len(mem._short_term) == 1

    def test_window_capping(self):
        mem = AgentMemory(window=3)
        for i in range(6):
            state = type("S", (), {"__dict__": {"pos": i, "health": 20.0}})()
            mem.record_observation(state)
        assert len(mem._short_term) <= 3

    def test_recent_messages(self):
        mem = AgentMemory(window=10)
        for i in range(5):
            mem.record_action(f"action_{i}", {"success": True, "message": "ok"})
        msgs = mem.recent_messages(3)
        assert len(msgs) == 3

    def test_recent_messages_all(self):
        mem = AgentMemory(window=10)
        for i in range(3):
            mem.record_action(f"action_{i}", {"success": True, "message": "ok"})
        msgs = mem.recent_messages()
        assert len(msgs) == 3

    def test_short_term_summary(self):
        mem = AgentMemory(window=5)
        mem.record_action("scan", {"success": True, "message": "Scanned"})
        summary = mem.short_term_summary
        assert "scan" in summary

    def test_empty_summary(self):
        mem = AgentMemory()
        s = mem.short_term_summary
        assert s == "" or s == "(no recent actions)"


class TestDeduplication:
    """Observation deduplication (I13)."""

    def test_duplicate_skipped(self):
        mem = AgentMemory(window=5)
        state = type("S", (), {"__dict__": {"position": (0, 65, 0), "health": 20.0}})()
        mem.record_observation(state)
        mem.record_observation(state)
        assert len(mem._short_term) == 1

    def test_changed_recorded(self):
        mem = AgentMemory(window=5)
        s1 = type("S", (), {"__dict__": {"position": (0, 65, 0), "health": 20.0}})()
        s2 = type("S", (), {"__dict__": {"position": (10, 65, 10), "health": 15.0}})()
        mem.record_observation(s1)
        mem.record_observation(s2)
        assert len(mem._short_term) == 2

    def test_dict_state(self):
        mem = AgentMemory(window=5)
        mem.record_observation({"position": (0, 65, 0), "health": 20.0})
        assert len(mem._short_term) == 1


class TestLongTermMemory:
    """Persistent fact storage."""

    def test_remember_fact(self):
        mem = AgentMemory()
        mem.remember_fact("Found diamond at y=11")
        assert "diamond" in mem.notable_facts()

    def test_deduplicate_facts(self):
        mem = AgentMemory()
        mem.remember_fact("X marks the spot")
        mem.remember_fact("X marks the spot")
        assert len(mem._long_term) == 1

    def test_empty_facts(self):
        mem = AgentMemory()
        assert mem.notable_facts() == ""

    def test_facts_capped(self):
        mem = AgentMemory()
        for i in range(20):
            mem.remember_fact(f"Fact {i}")
        facts = mem.notable_facts()
        assert facts.count("Fact ") == 10  # capped at 10


class TestPersistence:
    """SQLite persistence (N3)."""

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            m1 = AgentMemory(db_path=db)
            m1.remember_fact("Persistent fact")
            m1.close()
            m2 = AgentMemory(db_path=db)
            assert "Persistent fact" in m2.notable_facts()
            m2.close()
        finally:
            os.unlink(db)

    def test_no_db_by_default(self):
        mem = AgentMemory()
        assert mem._db_path == ""  # noqa: SLF001

    def test_env_var_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            old = os.environ.get("AGENT_MEMORY_DB")
            os.environ["AGENT_MEMORY_DB"] = db
            try:
                mem = AgentMemory()
                assert mem._db_path == db  # noqa: SLF001
                mem.close()
            finally:
                if old:
                    os.environ["AGENT_MEMORY_DB"] = old
                else:
                    del os.environ["AGENT_MEMORY_DB"]
        finally:
            os.unlink(db)

    def test_save_goal(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            mem = AgentMemory(db_path=db)
            mem.save_goal("Build a house")
            mem.close()
            assert os.path.getsize(db) > 0
        finally:
            os.unlink(db)

    def test_clear_all(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            mem = AgentMemory(db_path=db)
            mem.remember_fact("clear me")
            mem.clear_all()
            assert mem.notable_facts() == ""
            mem.close()
        finally:
            os.unlink(db)

    def test_db_fallback_on_bad_path(self):
        mem = AgentMemory(db_path="/nonexistent/dir/test.db")
        assert mem._db_path == ""  # falls back to in-memory
        mem.remember_fact("test")
        assert "test" in mem.notable_facts()


class TestMisc:
    """Edge cases and helpers."""

    def test_turn_count(self):
        mem = AgentMemory()
        assert mem.turn_count() == 0
        mem.record_action("a", {"success": True, "message": "ok"})
        assert mem.turn_count() >= 1

    def test_clear_short_term(self):
        mem = AgentMemory(window=5)
        mem.record_action("test", {"success": True, "message": "ok"})
        mem.clear_short_term()
        assert mem.short_term_summary == ""

    def test_role_assignment(self):
        mem = AgentMemory(window=5)
        mem.record_action("a", {"success": True, "message": "ok"})
        entry = mem._short_term[-1]
        assert entry.role == Role.ASSISTANT
        state = type("S", (), {"__dict__": {"pos": (0, 65, 0)}})()
        mem.record_observation(state)
        entry = mem._short_term[-1]
        assert entry.role == Role.USER
