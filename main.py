"""Controller: gather configuration, spin up Environment + Firefighter threads,
render the live dashboard, print a final report on termination.
"""
import os
import sys
import time
import random

from blackboard import Blackboard
from environment import Environment
from agent import FirefighterAgent
from utils import (
    RENDER_TICK, CELL_GLYPHS,
    INTACT, BURNING, EXTINGUISHED, ASH,
    RESET, DIM, BOLD, RED, GREEN, YELLOW, CYAN, WHITE, GRAY,
)


# --- Defaults (overridable at startup) ---
DEFAULT_ROWS              = 12
DEFAULT_COLS              = 20
DEFAULT_AGENTS            = 3
DEFAULT_FIRE_SEEDS        = 3
DEFAULT_FIRE_PROB         = 0.18
DEFAULT_BURN_DURATION     = 6
DEFAULT_MAX_TICKS         = 200
DEFAULT_DAMAGE_THRESHOLD  = 0.40
DEFAULT_VISIBILITY        = 4
MAX_AGENTS                = 26   # cap so each agent renders as one character


# ---------------- helpers ----------------

def _enable_ansi_on_windows():
    if os.name == "nt":
        os.system("")  # side-effect: enables VT processing in cmd/PowerShell


def _agent_glyph(idx):
    return str(idx) if idx < 10 else chr(ord("A") + idx - 10)


def _ask_int(prompt, default, lo=None, hi=None):
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        print(f"  invalid integer; using {default}")
        return default
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v


def _ask_float(prompt, default, lo=None, hi=None):
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        print(f"  invalid number; using {default}")
        return default
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v


def _outcome_styled(outcome):
    if outcome == Environment.OUTCOME_SUCCESS:
        return f"{GREEN}{BOLD}SUCCESS{RESET}"
    if outcome == Environment.OUTCOME_FAILURE:
        return f"{RED}{BOLD}FAILURE{RESET}"
    return f"{YELLOW}RUNNING{RESET}"


# ---------------- rendering ----------------

def _render(snapshot, outcome, num_agents, damage_threshold):
    grid = snapshot["grid"]
    positions = snapshot["agent_positions"]
    claims = snapshot["claims"]
    metrics = snapshot["metrics"]
    rows, cols = snapshot["rows"], snapshot["cols"]
    total = rows * cols

    disp = [[None] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            s = grid[r][c]
            g = CELL_GLYPHS[s]
            if   s == INTACT:       disp[r][c] = f"{GREEN}{g}{RESET}"
            elif s == BURNING:      disp[r][c] = f"{RED}{BOLD}{g}{RESET}"
            elif s == EXTINGUISHED: disp[r][c] = f"{CYAN}{g}{RESET}"
            elif s == ASH:          disp[r][c] = f"{GRAY}{g}{RESET}"

    # Overlay agents (last, so they sit on top of any cell)
    for aid, (ar, ac) in positions.items():
        glyph = _agent_glyph(aid)
        has_claim = any(owner == aid for owner in claims.values())
        style = (YELLOW + BOLD) if has_claim else (WHITE + BOLD)
        disp[ar][ac] = f"{style}{glyph}{RESET}"

    ash_pct = (metrics["ash"] / total * 100) if total else 0.0
    burn_pct = (metrics["burning"] / total * 100) if total else 0.0

    out = sys.stdout
    out.write("\033[H")
    out.write(f"{BOLD}=== WILDFIRE SUPPRESSION — Multi-Agent Simulation ==={RESET}\033[K\n")
    out.write(
        f"grid={rows}x{cols}  agents={num_agents}  "
        f"tick={metrics['tick']}  outcome={_outcome_styled(outcome)}\033[K\n"
    )
    out.write(
        f"  legend: {GREEN}.{RESET}=intact  {RED}*{RESET}=burning  "
        f"{CYAN}x{RESET}=extinguished  {GRAY}#{RESET}=ash  "
        f"{WHITE}#{RESET}=agent  {YELLOW}#{RESET}=agent-with-claim"
        "\033[K\n\n"
    )
    for row in disp:
        out.write(" ".join(row) + "\033[K\n")
    out.write("\n")
    out.write(
        f"  {BOLD}burning{RESET}={RED}{metrics['burning']}{RESET} ({burn_pct:.1f}%)   "
        f"{BOLD}ash{RESET}={GRAY}{metrics['ash']}{RESET} "
        f"({ash_pct:.1f}% / threshold {damage_threshold*100:.0f}%)   "
        f"{BOLD}extinguished{RESET}={CYAN}{metrics['extinguished']}{RESET}   "
        f"{BOLD}extinguish_acts{RESET}={metrics['extinguish_acts']}"
        "\033[K\n"
    )
    out.write(f"{DIM}Ctrl+C to stop.{RESET}\033[K\n")
    out.flush()


def _print_final_report(snapshot, outcome, env):
    metrics = snapshot["metrics"]
    total = snapshot["rows"] * snapshot["cols"]
    print()
    print(f"{BOLD}=== FINAL REPORT ==={RESET}")
    print(f"Outcome:                  {_outcome_styled(outcome)}")
    print(f"Ticks elapsed:            {metrics['tick']} (max {env.max_ticks})")
    print(f"Ash cells:                {metrics['ash']}/{total} "
          f"({metrics['ash']/total*100:.1f}% ; threshold {env.damage_threshold*100:.0f}%)")
    print(f"Cells extinguished:       {metrics['extinguished']}")
    print(f"Cells still burning:      {metrics['burning']}")
    print(f"Total extinguish actions: {metrics['extinguish_acts']}")
    per_agent = metrics["extinguish_per_agent"]
    if per_agent:
        print("Per-agent extinguishes:")
        for aid in sorted(per_agent):
            print(f"  agent {_agent_glyph(aid)}: {per_agent[aid]}")


# ---------------- main ----------------

def main():
    _enable_ansi_on_windows()

    print(f"{BOLD}--- SP2: Wildfire Suppression MAS — Configuration ---{RESET}")
    rows             = _ask_int  ("Grid rows",                              DEFAULT_ROWS,             lo=4, hi=40)
    cols             = _ask_int  ("Grid cols",                              DEFAULT_COLS,             lo=4, hi=80)
    num_agents       = _ask_int  ("Number of firefighter agents",           DEFAULT_AGENTS,           lo=1, hi=MAX_AGENTS)
    num_seeds        = _ask_int  ("Initial fire seeds",                     DEFAULT_FIRE_SEEDS,       lo=1, hi=max(1, rows * cols // 4))
    fire_prob        = _ask_float("Fire spread probability per neighbour",  DEFAULT_FIRE_PROB,        lo=0.0, hi=1.0)
    burn_duration    = _ask_int  ("Ticks before a burning cell becomes ash",DEFAULT_BURN_DURATION,    lo=1, hi=100)
    max_ticks        = _ask_int  ("Maximum simulation ticks",               DEFAULT_MAX_TICKS,        lo=1, hi=10000)
    damage_threshold = _ask_float("Damage threshold (fraction of grid)",    DEFAULT_DAMAGE_THRESHOLD, lo=0.01, hi=1.0)
    visibility       = _ask_int  ("Firefighter visibility radius",          DEFAULT_VISIBILITY,       lo=1, hi=max(rows, cols))

    all_cells = [(r, c) for r in range(rows) for c in range(cols)]
    fire_seeds = random.sample(all_cells, num_seeds)

    blackboard = Blackboard(rows, cols, fire_seeds, fire_prob, burn_duration)
    environment = Environment(blackboard, max_ticks, damage_threshold)

    # Place firefighters on random non-burning, non-occupied cells
    agents = []
    used = set(fire_seeds)
    for i in range(num_agents):
        tries = 0
        while True:
            r = random.randrange(rows)
            c = random.randrange(cols)
            if (r, c) not in used:
                used.add((r, c))
                break
            tries += 1
            if tries > 1000:
                break
        blackboard.register_agent(i, (r, c))
        agents.append(FirefighterAgent(i, (r, c), blackboard, visibility))

    sys.stdout.write("\033[2J")   # full clear once; later renders use cursor-home
    environment.start()
    for a in agents:
        a.start()

    try:
        while environment.is_alive():
            _render(blackboard.snapshot(), environment.outcome, num_agents, damage_threshold)
            time.sleep(RENDER_TICK)
        # One final render so the terminal state is visible
        _render(blackboard.snapshot(), environment.outcome, num_agents, damage_threshold)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted; stopping...{RESET}")
    finally:
        environment.stop()
        for a in agents:
            a.stop()
        for a in agents:
            a.join(timeout=1.0)
        environment.join(timeout=1.0)
        _print_final_report(blackboard.snapshot(), environment.outcome, environment)


if __name__ == "__main__":
    main()
