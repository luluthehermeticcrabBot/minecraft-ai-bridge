# P2 Prompt Context and Safe Retry Design

## Goal

Improve LLM recovery from failed actions without allowing unbounded prompt growth, blind repetition of side effects, or more than one action per turn.

## Behavior

1. Prompt context is assembled through bounded formatting helpers:
   - recent action/observation history is limited by entry count and character budget;
   - notable facts are limited by character budget while preserving newest facts;
   - the current goal and world state remain highest priority.
2. Failed actions produce an explicit retry hint containing:
   - action name;
   - failure message;
   - instruction to choose a different action or materially different parameters;
   - warning that the previous attempt may have partially changed the world.
3. A failed LLM-selected action creates at most one retry opportunity for the next turn.
   - The current turn still executes exactly one action.
   - The next turn's prompt contains the failure hint and fresh observation state.
   - The retry opportunity is consumed after that next decision, whether it succeeds or fails.
   - An identical action with identical parameters is rejected as a retry; the turn records a failure without executing a duplicate side effect.
   - Both attempts remain inspectable in short-term memory across turns.
4. A successful action clears any pending retry opportunity and ends the turn normally. Consecutive-failure accounting uses the executed action result.

## Boundaries

- No automatic parameter mutation or action-specific retry heuristics.
- No retry loop beyond one fresh LLM decision on the following turn.
- Existing public action, memory, and LLM client APIs remain unchanged.
- Existing provider implementations receive the same message model; only message construction and orchestrator control flow change.
- The existing one-observe → one-decision → one-action turn contract remains intact.

## Implementation Shape

- Add bounded memory rendering helpers in `bridge/memory.py`.
- Add failure-hint formatting in `llm/prompts.py`.
- Update `bridge/orchestrator.py` to include bounded memory/facts in the prompt and carry one guarded retry opportunity into the following turn.
- Keep retry bookkeeping explicit so observations and both action results remain inspectable.

## Verification

- Unit-test memory character bounds and newest-fact retention.
- Unit-test failure-hint content and identical-retry rejection.
- Unit-test one next-turn retry, successful retry, failed retry, and no retry for `wait`/`done`.
- Run the existing non-MCPQ suite and Ruff.
