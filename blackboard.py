"""Shared Blackboard owned by the Environment Agent.

Holds the authoritative grid state, the agent position table, and the
claim table (cell -> firefighter id). A single RLock mediates all access;
reads return consistent snapshots, writes are atomic. Firefighter agents
communicate only through this object.
"""
import threading
import random

from utils import INTACT, BURNING, EXTINGUISHED, ASH, neighbors4


class Blackboard:
    def __init__(self, rows, cols, fire_seeds, fire_prob, burn_duration):
        self.rows = rows
        self.cols = cols
        self.fire_prob = fire_prob
        self.burn_duration = burn_duration

        self.lock = threading.RLock()
        self.tick = 0

        self.grid = [[INTACT for _ in range(cols)] for _ in range(rows)]
        # Env-ticks each cell has been BURNING (0 when not burning)
        self.burn_age = [[0 for _ in range(cols)] for _ in range(rows)]
        for r, c in fire_seeds:
            self.grid[r][c] = BURNING

        # Coordination tables
        self.agent_positions = {}   # agent_id -> (r, c)
        self.claims = {}            # (r, c)   -> agent_id

        # Metrics
        self.metrics = {
            "tick":                  0,
            "burning":               len(fire_seeds),
            "extinguished":          0,
            "ash":                   0,
            "extinguish_acts":       0,
            "extinguish_per_agent":  {},
        }

    # ---------------- Perception ----------------

    def local_view(self, center, radius):
        """List of (cell, state, claimed_by) for cells within Chebyshev radius."""
        r0, c0 = center
        with self.lock:
            view = []
            for r in range(max(0, r0 - radius), min(self.rows, r0 + radius + 1)):
                for c in range(max(0, c0 - radius), min(self.cols, c0 + radius + 1)):
                    view.append(((r, c), self.grid[r][c], self.claims.get((r, c))))
            return view

    def cell_state(self, cell):
        with self.lock:
            r, c = cell
            return self.grid[r][c]

    # ---------------- Claim table ----------------

    def try_claim(self, agent_id, cell):
        """Atomically claim a burning cell. Refuses if already claimed by
        someone else, or if the cell is no longer burning."""
        with self.lock:
            r, c = cell
            if self.grid[r][c] != BURNING:
                return False
            owner = self.claims.get(cell)
            if owner is None or owner == agent_id:
                self.claims[cell] = agent_id
                return True
            return False

    def release_claim(self, agent_id, cell):
        with self.lock:
            if self.claims.get(cell) == agent_id:
                del self.claims[cell]

    # ---------------- Movement ----------------

    def register_agent(self, agent_id, pos):
        with self.lock:
            self.agent_positions[agent_id] = pos
            self.metrics["extinguish_per_agent"].setdefault(agent_id, 0)

    def try_move(self, agent_id, new_pos):
        with self.lock:
            r, c = new_pos
            if not (0 <= r < self.rows and 0 <= c < self.cols):
                return False
            for aid, pos in self.agent_positions.items():
                if aid != agent_id and pos == new_pos:
                    return False
            self.agent_positions[agent_id] = new_pos
            return True

    def occupied_cells(self, exclude_agent=None):
        with self.lock:
            return {pos for aid, pos in self.agent_positions.items()
                    if aid != exclude_agent}

    # ---------------- Actions ----------------

    def extinguish(self, agent_id, cell):
        """Turn a BURNING cell into EXTINGUISHED — only if `agent_id` is standing on it."""
        with self.lock:
            r, c = cell
            if self.agent_positions.get(agent_id) != cell:
                return False
            if self.grid[r][c] != BURNING:
                return False
            self.grid[r][c] = EXTINGUISHED
            self.burn_age[r][c] = 0
            self.metrics["extinguish_acts"] += 1
            self.metrics["extinguish_per_agent"][agent_id] += 1
            self.release_claim(agent_id, cell)
            return True

    # ---------------- Environment advancement ----------------

    def advance_fire(self):
        """One tick of stochastic fire propagation. Called by the Environment Agent."""
        with self.lock:
            self.tick += 1

            # 1. Age burning cells; promote to ASH past burn_duration
            new_ash = []
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.grid[r][c] == BURNING:
                        self.burn_age[r][c] += 1
                        if self.burn_age[r][c] >= self.burn_duration:
                            new_ash.append((r, c))
            for r, c in new_ash:
                self.grid[r][c] = ASH
                self.burn_age[r][c] = 0
                if (r, c) in self.claims:
                    del self.claims[(r, c)]

            # 2. Each burning cell rolls to ignite each INTACT neighbour
            ignitions = []
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.grid[r][c] != BURNING:
                        continue
                    for nr, nc in neighbors4(r, c, self.rows, self.cols):
                        if self.grid[nr][nc] == INTACT and random.random() < self.fire_prob:
                            ignitions.append((nr, nc))
            for r, c in ignitions:
                if self.grid[r][c] == INTACT:
                    self.grid[r][c] = BURNING

            self._refresh_metrics()
            return self.tick

    def _refresh_metrics(self):
        burning = ext = ash = 0
        for row in self.grid:
            for cell in row:
                if   cell == BURNING:      burning += 1
                elif cell == EXTINGUISHED: ext += 1
                elif cell == ASH:          ash += 1
        self.metrics["tick"]         = self.tick
        self.metrics["burning"]      = burning
        self.metrics["extinguished"] = ext
        self.metrics["ash"]          = ash

    def total_cells(self):
        return self.rows * self.cols

    # ---------------- Renderer snapshot ----------------

    def snapshot(self):
        with self.lock:
            return {
                "grid":            [row[:] for row in self.grid],
                "agent_positions": dict(self.agent_positions),
                "claims":          dict(self.claims),
                "metrics": {
                    **self.metrics,
                    "extinguish_per_agent": dict(self.metrics["extinguish_per_agent"]),
                },
                "rows": self.rows,
                "cols": self.cols,
                "tick": self.tick,
            }
