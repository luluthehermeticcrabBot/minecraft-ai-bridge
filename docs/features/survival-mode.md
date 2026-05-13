# Survival Mode

> Status: Planned (P3)  
> Depends on: N2 (WASD Movement), N1 (Inventory Manager)

## Goal

Enable the agent to survive and thrive in survival mode — hunt for food, defend against hostile mobs, manage health and hunger, and progress through the tech tree without creative-mode `/give`.

## Phased Approach

### Phase 1: WASD Movement (prerequisite)
See `wasd-movement.md`. Survival mode requires physics-based movement.

### Phase 2: Survival Crafting
Replace creative-mode `/give` with actual survival crafting:
- **Recipe database**: Hardcode essential vanilla recipes (or load via `/recipe`)
- **Crafting table interaction**: `/setblock crafting_table`, then use clicks / data
- **Furnace smelting**: Place furnace, add fuel + ore, wait for smelt
- **Tool tier progression**: Wood → Stone → Iron → Diamond
- **Enchanting**: Enchantment table + lapis + levels

### Phase 3: Hunting & Food

#### Hunting Philosophy
The agent hunts **only when necessary** to accomplish its goal (staying
alive, gathering resources). It does NOT kill for sport. Mobs are
classified by risk-to-reward ratio — the agent must never engage in
combat where the risk to its survival outweighs the benefit.

#### Passive Mobs (safe to hunt)
- Cow → beef (smelt → steak), leather
- Pig → porkchop (smelt → cooked porkchop)
- Chicken → chicken (smelt → cooked chicken), feathers, eggs
- Sheep → mutton (smelt → cooked mutton), wool
- Rabbit → rabbit (smelt → cooked rabbit), rabbit hide
- Salmon / Cod → cooked fish

#### Neutral Mobs (conditional — leave alone unless attacked)
- Wolf → only if attacked first (risk: pack retaliation)
- Dolphin → never (protected, no food benefit)
- Llama → only if attacked first (risk: spitting, pack)
- Bee → never (risk: swarm, environmental damage)
- Fox → avoid (low food value, fast)

#### Prohibited Targets (never hunt unless explicitly instructed by user goal)
- **Villagers** — essential for trading, part of village economy. Killing
  them breaks trading relationships and is irreversible.
- **Illagers** — too dangerous (Vindicator axe deals 19 damage), no food
  benefit. Only engage in self-defence.
- **Iron Golems** — extremely dangerous (21 damage), defensive only.
- **Pillagers** — ranged crossbows, patrol in groups. Avoid unless they
  are directly blocking progress AND retreat is impossible.
- **Witches** — splash potions of poison/slowness, drink healing.
  Too risky for marginal benefit.
- **Endermen** — teleport, 21 damage. Extremely high risk. Never engage
  unless absolutely necessary (e.g., Ender Dragon fight).
- **Zombified Piglins** — neutral unless provoked. In the Nether,
  provoking one triggers the entire horde. Never attack.

#### Hostile Mobs (tactical engagement)

These mobs **auto-attack the player on sight** and must be dealt with
when they block progress:

| Mob | Threat | Strategy | Food/Item |
|-----|--------|----------|-----------|
| Zombie | Medium | Melee with sword, spacing | Rotten flesh (only eat if starving + no alternatives) |
| Skeleton | High | Close gap with blocks, strafe | Bones, arrows |
| Creeper | Very High | Back away, ranged attack or shield | Gunpowder |
| Spider | Medium | Melee, climb-proof area | String |
| Hoglin | Medium | Melee, fire res in Nether | Porkchop (good food) |
| Slime | Low | Easy melee | Slimeballs |

Attack priority:
- If mob is actively attacking → defend first, hunt second
- If mob is between agent and goal → tactical elimination
- If mob is far / ignoreable → leave alone

#### Attack Protocol
```
1. Detect mob via scan (entity type + distance)
2. If passive & needs food → approach, attack
3. If neutral & not attacking → leave alone
4. If hostile & attacking → defend immediately (see Phase 4)
5. If hostile & in the way → tactical elimination
6. Use appropriate weapon (sword > axe > fist)
7. Retreat if health < 10 (5 hearts)
8. After threat eliminated → eat if hungry → resume goal
```

#### Risk Assessment Matrix
When deciding whether to engage a mob, the agent considers:
- **Current health**: Below 10HP (5 hearts) → retreat, never engage
- **Current armor**: No armor → avoid all hostile mobs
- **Current weapon**: Fist only → avoid armored/skelly mobs
- **Mob count**: 3+ mobs in area → retreat, reassess
- **Time of day**: Night → mobs spawn faster, be more cautious
- **Biome**: Nether → always be defensive, never chase

### Phase 4: Self-Defense

#### Hostile Mob Threat Assessment
| Mob | Threat Level | Strategy |
|-----|-------------|----------|
| Zombie | Medium | Melee with sword, keep distance |
| Skeleton | High | Close gap with blocks, ranged attack |
| Creeper | Very High | Back away, ranged attack or shield |
| Spider | Medium | Melee, watch for wall-climbing |
| Enderman | Very High | Don't look at - run if provoked |
| Witch | High | Rush down, fire resistance potion |
| Blaze | High | Snowballs or ranged |
| Hoglin | Medium | Melee, fire resistance in Nether |

#### Defensive Protocol
```
if hostile mob detected within 15 blocks:
  1. Equip best weapon + shield
  2. Assess mob type + distance
  3. If creeper within 5 blocks → sprint away (WASD)
  4. If skeleton → build wall/approach zigzag
  5. If zombie → melee with spacing
  6. If health < 5 hearts → retreat + eat + heal
  7. After threat eliminated → resume goal
```

### Phase 5: YOLO-based Fast Threat Detection

**Problem**: Vision LLM inference (GPT-4o, Claude) takes 2-5 seconds per
frame — too slow for self-defense. At 20 ticks/second, a creeper can
explode in 1.5 seconds (30 ticks). Even a fast vision LLM response is
10+ ticks, by which time the agent has already taken damage.

**Solution**: Lightweight YOLO model for real-time threat detection
(1-5ms per frame on GPU, 20-50ms on CPU).

#### Architecture
```
[MCPQ Screenshot / Map render]
        ↓
[YOLOv8n (1-5ms GPU, 20-50ms CPU)]
        ↓
[Bounding boxes + class labels + confidence scores]
        ↓
[Threat assessment: type, distance estimate, count]
        ↓
[Combat decision: retreat / engage / ignore]
        ↓
[LLM receives structured threat report (not raw pixels)]
```

- YOLO runs in a background task every ~1 second
- When a threat is detected (hostile mob within 15 blocks), the agent
  enters **combat mode** — it pre-empts the normal think-act-observe
  loop with a faster "react" cycle
- The LLM still handles strategic decisions; YOLO handles reactive
  fast-path decisions (dodge, block, sprint)
- The output of YOLO is fed as structured text to the LLM ("Zombie 8
  blocks northeast, confidence 0.94") so the LLM has threat awareness
  without needing vision inference latency on the critical path

#### Model Selection

| Model | Size | GPU (ms) | CPU (ms) | mAP@0.5 | Use Case |
|-------|------|----------|----------|---------|----------|
| YOLOv8n | 3.2MB | 1-2 | 20-30 | ~37 | Primary — fastest |
| YOLOv8s | 11MB | 2-3 | 30-50 | ~44 | If more accuracy needed |
| YOLOv8m | 26MB | 3-5 | 50-80 | ~50 | If running on GPU |
| RT-DETR-L | 32MB | 5-8 | N/A | ~53 | If accuracy > speed |

**Recommendation**: Start with YOLOv8n (nano). It can run on CPU at
~30-50fps which is sufficient for 1-second threat checks.

#### Training Approach

Option A — **Fine-tune a pre-trained model** (Recommended):
1. Start with YOLOv8n pre-trained on COCO
2. Collect 500-1000 Minecraft screenshots with mob annotations
3. Fine-tune for 50-100 epochs (1-2 hours on consumer GPU)
4. Export to ONNX for cross-platform inference

Option B — **Use existing Minecraft detection model**:
- RoboFlow Universe has several Minecraft mob detection models
- Trade-off: less control over class definitions
- Good for prototyping, less ideal for production

Option C — **Zero-shot with YOLO-World**:
- YOLO-World can detect arbitrary classes from text prompts
- No training needed, but higher latency (~50ms)
- Useful fallback for detecting unexpected mob types

#### Integration With Bridge

```python
class ThreatDetector:
    """Background task that runs YOLO inference and produces threat alerts."""

    def __init__(self, mc: McpqClient, memory: AgentMemory):
        self._model = YOLO("minecraft-mob-detector.pt")  # fine-tuned
        self._mc = mc
        self._memory = memory
        self._latest_threats: list[Threat] = []

    async def run_cycle(self):
        """Called every ~1 second from a background task."""
        # Capture screenshot via MCPQ (or map render)
        pixels = await self._capture_view()
        # Run YOLO inference (in thread — it's blocking)
        results = await asyncio.to_thread(self._model, pixels)
        threats = self._parse_threats(results)
        self._latest_threats = threats
        if any(t.is_hostile and t.distance < 15 for t in threats):
            self._memory.remember_fact(
                f"Threat detected: {[str(t) for t in threats]}"
            )
            return ThreatAlert(level="danger", threats=threats)
        return None
```

#### Risk: False Positives / Negatives

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| False positive (safe mob flagged as hostile) | Agent wastes time in combat mode | Set confidence threshold at 0.6+ |
| False negative (hostile mob not detected) | Agent takes damage | Redundant check: LLM can also scan via MCPQ; combine both signals |
| Partial occlusion (mob behind tree) | Missed detection | Lower threshold + temporal consistency (detected in 2/3 frames) |

#### Training Data Sources
- RoboFlow: "Minecraft Mob Detection" dataset (3.5k images)
- Kaggle: "Minecraft Entities Detection" (~900 images)
- Synthetic: Render Minecraft entities on random backgrounds
- Self-supervised: Run the agent, take screenshots, manually annotate
  edge cases (goal: 200-300 frames from own server for domain adaptation)

#### Deployment Consideration
- YOLO runs **in the bridge container**, not on the Minecraft server
- ONNX Runtime for CPU inference (no GPU needed in initial version)
- Model weights shipped with the bridge or downloaded on first run
- If no GPU: YOLOv8n on CPU gives 20-30ms → acceptable for 1s cycle
- The threat detector should be **optional/pluggable** — the agent works
  without it, but has faster reactions with it

### Phase 6: Full Survival Autonomy

- Mine diamond → enchant gear → defeat Ender Dragon
- Auto-farming: plant → grow → harvest → replant
- Nether preparation: fire resistance, portal building
- The End: locate stronghold, activate portal, defeat dragon

## Implementation Effort

| Phase | Components | Est. Effort | Dependencies |
|-------|-----------|-------------|--------------|
| 1 | WASD movement | 3-5 days | — |
| 2 | Survival crafting | 5-7 days | Phase 1 |
| 3 | Mob hunting | 3-5 days | Phase 1, + weapon system |
| 4 | Self-defense | 3-5 days | Phase 1, + health tracking |
| 5 | YOLO integration | 5-7 days | Phase 4, screenshot pipeline |
| 6 | Full autonomy | Ongoing | All above |

## References

- YOLOv8: https://github.com/ultralytics/ultralytics
- Minecraft Mob Detection Dataset: https://universe.roboflow.com/minecraft-1frcb/minecraft-mob-detection
- Paper 26.1 entity damage mechanics documentation
- Vanilla crafting recipe format
