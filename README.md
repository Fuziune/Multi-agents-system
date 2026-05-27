# SP2 — Wildfire Suppression Multi-Agent System

A from-scratch Python MAS (no external agent frameworks) that simulates a
team of firefighter agents containing a stochastic wildfire on a 2D grid.

Matches the spec defined in `main.tex` (Component 4):

- **Two agent types:** N concurrent firefighter threads + 1 Environment Agent.
- **Communication:** shared, lock-protected blackboard with grid, agent
  positions, and claim table.
- **Strategy (MVP):** nearest-fire greedy. (Region partitioning to be added
  in a later component.)
- **Configurable at startup:** grid size, agent count, fire seeds, spread
  probability, burn duration, max ticks, damage threshold, visibility radius.

## Run

```bash
python main.py
```

All prompts have defaults — press Enter to accept. Press `Ctrl+C` to interrupt;
a final report is printed on exit.

## Files

| File             | Responsibility                                                       |
| ---------------- | -------------------------------------------------------------------- |
| `main.py`        | Config prompt, orchestration, ANSI dashboard, final report           |
| `blackboard.py`  | Shared state owned by the Environment Agent; locked grid & claims    |
| `environment.py` | `Environment(Thread)` — advances fire ticks, checks SUCCESS/FAILURE  |
| `agent.py`       | `FirefighterAgent(Thread)` — sense (local view) / select / act       |
| `utils.py`       | Constants, cell-state glyphs, ANSI colors, BFS pathfinder            |

## Cell states & glyphs

| Glyph | State          | Color  |
| ----- | -------------- | ------ |
| `.`   | INTACT         | green  |
| `*`   | BURNING        | red    |
| `x`   | EXTINGUISHED   | cyan   |
| `#`   | ASH (lost)     | gray   |
| `0–9 / A–P` | Firefighter — white=searching, yellow=has claim | — |

## Coordination protocol (claim table)

Before walking toward a fire, a firefighter publishes a claim on the
blackboard: `(r, c) -> agent_id`. Other firefighters see the claim during
their next sense step and exclude already-claimed cells from their candidate
targets. Claims are released when the target is extinguished, becomes ash,
or the owner abandons it.

## Terminal conditions (checked every env-tick)

- `FAILURE` if `ash_fraction >= damage_threshold` at any point
- `FAILURE` if `tick >= max_ticks`
- `SUCCESS` if `burning == 0` (and FAILURE has not been tripped)

## Metrics

- `tick`, `burning`, `ash`, `extinguished` — live in the dashboard
- `extinguish_acts` total and per-agent breakdown — printed in the final report
- Outcome and ticks elapsed — printed in the final report

## Threading model

| Thread                  | Count | Owns / does                                          |
| ----------------------- | ----- | ---------------------------------------------------- |
| Main thread             | 1     | Reads config, spawns others, renders, prints report  |
| `Environment`           | 1     | Advances fire every ENV_TICK, checks terminal state  |
| `FirefighterAgent`      | N     | Sense → claim → BFS → move → extinguish (per AGENT_TICK) |

All shared state lives in `Blackboard` and is guarded by a single `RLock`.
