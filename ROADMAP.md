# Project Roadmap

> **Minecraft AI Bridge** - Development Roadmap and Priority Tracking
> Last Updated: 2026-08-26

This document outlines the development priorities, completed work, and future plans for the Minecraft AI Bridge project.

---

## 🎯 Current Status

**Version**: 0.5.1 (unreleased)
**Test Coverage**: 319 deterministic tests passing; integration tests require Paper/MCPQ and an LLM provider
**Overall Health**: ✅ Core behavior stable; CI and release hardening in progress

---

## ✅ Completed Milestones

### P0: Critical Fixes (All Complete)
- [x] Fixed all confirmed bugs (B1-B19, see `docs/bugs.md`)
- [x] B1: Turn left/right command format
- [x] B2: Craft item uses `/give` (documented limitation)
- [x] B3: Drop item now spawns entities
- [x] B4: Goal tree parent tracking uses object references
- [x] B5-B8: OpenCode session management, config validation, logging
- [x] B9: Inventory NBT parsing into structured data
- [x] B12: Biome detection via surface block heuristics
- [x] B13: Consecutive failure protection with graceful shutdown
- [x] B14: Safe string formatting (string.Template)
- [x] B15: Ollama JSON mode with fallback
- [x] B16: botsummon retry with polling
- [x] B17: Memory deduplication
- [x] B18-B19: Chat commands and inventory refresh

### P1: High Priority (All Complete)
- [x] I2: Structured inventory parsing (`InventorySlot`, `_parse_inventory_nbt()`)
- [x] I3: Health parsing as float (`_parse_nbt_value()`)
- [x] I4: Biome detection (`McpqClient.get_biome()`, `WorldState.biome`)
- [x] I5: Safe string formatting for LLM prompts
- [x] I6: Error loop protection (consecutive failures → graceful shutdown)
- [x] I7: Type annotations for handlers
- [x] I8: RCON deprecation (marked in docs)
- [x] I9: Pre-commit hooks configuration
- [x] I11: Ollama compatibility (graceful fallback for JSON mode)
- [x] I12: Configurable botsummon retry (10 attempts at 1s intervals)
- [x] I13: Memory deduplication (skip unchanged observations)

### P1: New Features (Phase 4 - All Complete)
- [x] I25: Persistent memory (SQLite-backed facts survive restarts)
- [x] I26: In-game chat commands (`!status`, `!stop`, `!goal`, `!goto`, `!follow`, `!come`)
- [x] I27: Structured inventory manager (`has_item()`, `count_item()`, `get_summary()`)
- [x] I28: Structure respect rules (prompt guidance to not build over existing builds)

### Testing
- [x] 319 deterministic tests passing (MockMcpqClient-based, no server needed)
- [ ] Integration tests require Paper/MCPQ and an LLM provider
- [x] Goal-verification helpers (`actions_taken()`, `position_reached()`)

### P2: Observer and Prompt Reliability (Complete)
- [x] Observer hardening: robust inventory SNBT, health parsing, and authoritative dimension-aware biome detection
- [x] Bounded prompt context and notable facts
- [x] Explicit failure-recovery hints with one guarded next-turn retry
- [x] Identical retry rejection without repeating side effects

---

## 🚀 Upcoming Priorities

### P1: Release Readiness (Current)

#### CI/CD Setup
- [ ] **Set up GitHub Actions secrets** for integration tests
  - `OPENROUTER_API_KEY` for LLM inference tests
  - Consider `MISTRAL_API_KEY` as alternative
- [x] Run deterministic unit tests on all pushes and pull requests
- [x] Gate integration tests on the configured provider secret
- [x] Run Ruff linting and formatting checks
- [ ] Re-enable mypy after reconciling strict SDK types
- [ ] **Add test matrix** for Python versions (3.11, 3.12, 3.13)

#### Code Improvements
- [x] Fix auto-step logic to not step over hazards
- [x] Update command format tests to match current code
- [x] Add fallback plans for Nether portal construction, End portal activation,
  redstone circuits, animal farming, and villager trading

### P2: Medium Priority (Next Month)

#### Movement System
- [ ] **WASD-style movement** (Phase 4 feature)
  - Replace teleport-based movement with physics-based walking
  - Requires MCPQ plugin support or command-based simulation
  - Implement proper collision detection
  - Add momentum and inertia

#### Survival Mode Support
- [x] **Health and hunger management**
  - Monitor and maintain health
  - Find and consume food
  - Avoid dangerous situations
- [x] **Mob detection and reflex combat**
  - Detect nearby mobs and avoid dangerous situations
  - Attack manageable threats and flee from overwhelming threats
- [ ] **Weapon selection and usage**
  - [x] Select and equip strongest supported melee weapon in the hotbar
  - [ ] Extend selection to main-inventory transfer and broader loadout policy
- [ ] **Armor management**
- [ ] **Proper crafting** (not just `/give`)
  - Recipe matching
  - Crafting table interaction
  - Smelting and processing

#### Pathfinding Enhancements
- [ ] **3D pathfinding** (not just XZ plane)
- [ ] **Jump/parkour capabilities**
- [ ] **Avoidance of player-built structures**
- [ ] **Better obstacle detection**

#### Planning System
- [ ] **Multi-turn planning**
  - Allow LLM to plan multiple steps ahead
  - Implement plan validation

### P3: Low Priority (Future)

#### Infrastructure
- [ ] **Health check endpoint** for bridge service
- [ ] **Log rotation / structured logging**
- [ ] **mypy strict mode** configuration
- [ ] **PyPI publishing pipeline**
  - Set up `pypi-publish` workflow
  - Version management
  - Package metadata
- [ ] **Add `__all__`** to all public modules
- [ ] **Config schema generation** (JSON Schema from pydantic)

#### Multi-Agent Support
- [ ] **Multiple AI agents** in same world
- [ ] **Coordination between agents**
- [ ] **Task delegation**

#### Advanced Features
- [ ] **Structure preservation**
  - Detect existing player builds
  - Avoid building over structures
  - Respect village boundaries
- [ ] **Biome awareness**
  - Detect current biome
  - Biome-specific strategies
  - Resource location by biome
- [ ] **Time-based behaviors**
  - Day/night cycles
  - Sleep in beds at night
  - Avoid hostile mobs at night

---

## 📋 Release Plan

### v0.5.0
- All critical bugs fixed
- Phase 4 features complete (chat commands, inventory manager, persistent memory)

### v0.5.1 (Current, unreleased)
**Focus**: Observer hardening and prompt recovery

- [x] Robust inventory, health, and biome observation
- [x] Bounded prompt context and notable facts
- [x] Failure hints and one guarded next-turn retry

### v0.6.0 (Next Minor Release)
**Target**: 2-4 weeks
**Focus**: CI/CD matrix and remaining survival basics

- [x] GitHub Actions CI with deterministic unit tests
- [ ] Configure `OPENROUTER_API_KEY` repository secret for integration tests
- [ ] Add Python 3.11, 3.12, and 3.13 test matrix
- [x] Health and hunger management
- [x] Mob detection and reflex combat
- [ ] Weapon selection, armor management, and proper crafting/smelting

### v0.7.0
**Target**: 1-2 months
**Focus**: Movement, pathfinding, and planning improvements

- [ ] WASD-style movement
- [ ] 3D pathfinding
- [ ] Jump/parkour capabilities
- [ ] Multi-turn planning
- [ ] PyPI publishing

### v1.0.0 (Stable Release)
**Target**: 3-6 months
**Focus**: Production readiness, full feature set

- [ ] All P1 and P2 items complete
- [ ] Comprehensive documentation
- [ ] Performance optimization
- [ ] Security audit
- [ ] User testing and feedback

---

## 🧪 Testing Strategy

### Unit Tests (319 deterministic tests)
- **Run in CI**: ✅ Yes (on all pushes/PRs)
- **Dependencies**: None (MockMcpqClient)
- **Coverage**: Action handlers, NBT parsing, memory, goals, config, inventory, chat commands, pathfinding, and orchestrator recovery

### Integration Tests
- **Run in CI**: ⚠️ Only with `OPENROUTER_API_KEY`
- **Dependencies**: Paper server + MCPQ plugin + LLM provider
- **Coverage**: Full think-act-observe loop and provider-backed inference

### Manual Testing
- **Local Docker setup**: Required for full end-to-end testing
- **LLM providers**: Test with OpenAI, Anthropic, Ollama, OpenRouter, OpenCode Server
- **Minecraft versions**: Test with Paper 26.1.2
---


## 🔧 Development Workflow

### Branching Strategy
- **main/master**: Stable releases only
- **feature/***: New features (PR to main)
- **fix/***: Bug fixes (PR to main)
- **vibe/***: AI agent work (PR to main)

### Pull Request Requirements
- [ ] All unit tests pass
- [ ] Code follows project conventions
- [ ] Documentation updated
- [ ] Changelog entry added

### Commit Messages
- Use imperative mood ("Fix bug" not "Fixed bug")
- Include issue/PR references
- Keep first line under 50 chars
- Add detailed description if needed

---

## 📊 Success Metrics

| Metric | Current | Target (v1.0) |
|--------|---------|---------------|
| Unit Test Coverage | 190 tests | 200+ tests |
| Integration Tests | 22 tests | 30+ tests |
| Bug Count | ~5 minor | 0 critical |
| Documentation | 90% complete | 100% complete |
| CI Status | ⚠️ Partial | ✅ Full |
| PyPI Package | ❌ Not published | ✅ Published |

---

## 🤝 Contribution Guidelines

### Getting Started
1. Fork the repository
2. Clone and install: `pip install -e ".[dev]"`
3. Run tests: `pytest tests/ -k "not integration"`
4. Pick an issue from the roadmap

### Code Review
- Follow project conventions (see `AGENTS.md`)
- Add tests for new functionality
- Update documentation
- Keep changes focused and small

### Reporting Issues
- Include steps to reproduce
- Expected vs actual behavior
- Config (provider, model, mode)
- Relevant log output

---

## 📞 Support

- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: General questions and ideas
- **Documentation**: README.md, docs/, AGENTS.md

---

*This roadmap is a living document and will be updated as priorities shift and new requirements emerge.*
