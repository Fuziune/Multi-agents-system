"""Firefighter Agent (threaded). Communicates only through the Blackboard.

Strategy: NEAREST-FIRE GREEDY
  1. Sense:  read local view (Chebyshev radius) from the blackboard.
  2. Select: pick nearest BURNING cell that is unclaimed (or already mine);
             atomically publish a claim on the blackboard.
  3. Act:    BFS to it (avoiding other agents and burning cells in the way);
             on arrival, extinguish it and release the claim.
"""
import threading
import time
import random

from utils import AGENT_TICK, BURNING, bfs_path, manhattan


class FirefighterAgent(threading.Thread):
    def __init__(self, agent_id, initial_pos, blackboard, visibility_radius):
        super().__init__(daemon=True)
        self.agent_id = agent_id
        self.pos = initial_pos
        self.blackboard = blackboard
        self.visibility_radius = visibility_radius

        self.target = None     # claimed burning cell (or None)
        self.path = []         # planned route (excludes current pos)
        self.running = True

    # ---------------- Thread lifecycle ----------------

    def run(self):
        while self.running:
            try:
                self.sense_select_act()
            except Exception as exc:
                print(f"[firefighter {self.agent_id}] error: {exc}")
            time.sleep(AGENT_TICK)

    def stop(self):
        self.running = False

    # ---------------- Sense / Select / Act ----------------

    def sense_select_act(self):
        view = self.blackboard.local_view(self.pos, self.visibility_radius)

        # Drop a stale target (no longer burning, e.g. it became ASH)
        if self.target is not None:
            if self.blackboard.cell_state(self.target) != BURNING:
                self.blackboard.release_claim(self.agent_id, self.target)
                self.target = None
                self.path = []

        # Acquire a target if we don't have one
        if self.target is None:
            candidate = self._pick_target(view)
            if candidate is None:
                self._wander()
                return
            if not self.blackboard.try_claim(self.agent_id, candidate):
                # Another firefighter claimed it first this tick
                return
            self.target = candidate
            self.path = self._plan(self.target)

        # If standing on the target, extinguish it
        if self.pos == self.target:
            self.blackboard.extinguish(self.agent_id, self.target)
            self.target = None
            self.path = []
            return

        self._step()

    def _pick_target(self, view):
        """Nearest BURNING cell that is unclaimed (or already ours)."""
        candidates = []
        for cell, state, owner in view:
            if state != BURNING:
                continue
            if owner is not None and owner != self.agent_id:
                continue
            candidates.append(cell)
        if not candidates:
            return None
        return min(candidates, key=lambda c: manhattan(self.pos, c))

    # ---------------- Movement ----------------

    def _plan(self, goal):
        bb = self.blackboard
        occupied = bb.occupied_cells(exclude_agent=self.agent_id)
        grid = bb.snapshot()["grid"]

        # Other firefighters and active fires block routing.
        # The goal cell is exempt (it's burning — that's the whole point).
        def is_passable(cell):
            if cell in occupied:
                return False
            r, c = cell
            return grid[r][c] != BURNING

        path = bfs_path(self.pos, goal, bb.rows, bb.cols, is_passable)
        if not path or len(path) < 2:
            return []
        return path[1:]

    def _step(self):
        if not self.path:
            self.path = self._plan(self.target)
            if not self.path:
                return

        next_cell = self.path[0]
        if self.blackboard.try_move(self.agent_id, next_cell):
            self.pos = next_cell
            self.path.pop(0)
            return

        # Blocked — force replan next tick
        self.path = []

    def _wander(self):
        """Random orthogonal step (or stay) into a safe cell to discover fire."""
        r, c = self.pos
        options = [(r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        random.shuffle(options)
        for cand in options:
            cr, cc = cand
            if not (0 <= cr < self.blackboard.rows and 0 <= cc < self.blackboard.cols):
                continue
            if self.blackboard.cell_state(cand) == BURNING:
                continue
            if self.blackboard.try_move(self.agent_id, cand):
                self.pos = cand
                return
