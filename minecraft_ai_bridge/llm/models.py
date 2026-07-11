"""Pydantic models for LLM interaction."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in the conversation with the LLM."""

    role: Role
    content: str


class MemoryEntry(BaseModel):
    """A remembered observation or action stored for context."""

    turn: int
    role: Role
    summary: str
    raw: str = ""


class ToolCall(BaseModel):
    """A tool/function call requested by the LLM."""

    id: str = ""
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    """Structured response from the LLM (for text-mode parsing)."""

    thought: str = ""
    action: str = ""
    action_params: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""

    @classmethod
    def from_tool_call(cls, tool_call: ToolCall) -> LLMResponse:
        """Build an LLMResponse from a tool-call request."""
        return cls(
            thought="",
            action=tool_call.name,
            action_params=tool_call.arguments,
            reasoning=tool_call.arguments.get("reasoning", ""),
        )


class AgentGoal(BaseModel):
    """A goal the agent is working toward."""

    description: str
    priority: int = 0
    completed: bool = False
    sub_goals: list[AgentGoal] = Field(default_factory=list)
    parent_goal: str | None = None
    depth: int = 0

    # Private: object reference to parent for navigating the goal tree.
    # Not serialised — set by GoalManager when building the tree.
    _parent_ref: AgentGoal | None = None

    @property
    def active_sub_goal(self) -> AgentGoal | None:
        """Return the first incomplete sub-goal."""
        for sg in self.sub_goals:
            if not sg.completed:
                return sg
        return None
