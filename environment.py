"""Environment Agent — passive coordinator that owns the Blackboard.

Each ENV_TICK it advances fire propagation by one step and checks whether
the simulation has reached a terminal state (SUCCESS or FAILURE).
"""
import threading
import time

from utils import ENV_TICK


class Environment(threading.Thread):
    OUTCOME_RUNNING = "RUNNING"
    OUTCOME_SUCCESS = "SUCCESS"
    OUTCOME_FAILURE = "FAILURE"

    def __init__(self, blackboard, max_ticks, damage_threshold):
        super().__init__(daemon=True)
        self.blackboard = blackboard
        self.max_ticks = max_ticks
        self.damage_threshold = damage_threshold   # fraction of grid that may become ASH

        self.outcome = self.OUTCOME_RUNNING
        self.running = True

    def run(self):
        while self.running:
            tick = self.blackboard.advance_fire()
            self._check_terminal(tick)
            if self.outcome != self.OUTCOME_RUNNING:
                self.running = False
                return
            time.sleep(ENV_TICK)

    def stop(self):
        self.running = False

    def _check_terminal(self, tick):
        m = self.blackboard.metrics
        total = self.blackboard.total_cells()
        ash_fraction = (m["ash"] / total) if total else 0.0

        if ash_fraction >= self.damage_threshold:
            self.outcome = self.OUTCOME_FAILURE
            return
        if m["burning"] == 0:
            self.outcome = self.OUTCOME_SUCCESS
            return
        if tick >= self.max_ticks:
            self.outcome = self.OUTCOME_FAILURE
