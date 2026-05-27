"""Constants, cell-state codes, ANSI styling, BFS pathfinder."""
from collections import deque

# --- Simulation timing (seconds) ---
AGENT_TICK  = 0.30   # delay between firefighter sense-act cycles
ENV_TICK    = 0.50   # delay between environment fire-propagation ticks
RENDER_TICK = 0.40   # delay between full UI redraws

# --- Cell states ---
INTACT       = 0
BURNING      = 1
EXTINGUISHED = 2
ASH          = 3

CELL_GLYPHS = {
    INTACT:       '.',
    BURNING:      '*',
    EXTINGUISHED: 'x',
    ASH:          '#',
}

# --- ANSI styling ---
RESET   = "\033[0m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"
GRAY    = "\033[90m"


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r, c, rows, cols):
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            yield (nr, nc)


def bfs_path(start, goal, rows, cols, is_passable):
    """4-connected BFS from `start` to `goal`.

    `is_passable(cell)` decides traversability for intermediate cells.
    The goal cell is always allowed (so an agent can stand on a burning
    target to extinguish it). Returns [start, ..., goal] or None.
    """
    if start == goal:
        return [start]
    visited = {start}
    queue = deque([(start, [start])])
    while queue:
        (r, c), path = queue.popleft()
        for nr, nc in neighbors4(r, c, rows, cols):
            cell = (nr, nc)
            if cell in visited:
                continue
            if cell == goal:
                return path + [cell]
            if not is_passable(cell):
                continue
            visited.add(cell)
            queue.append((cell, path + [cell]))
    return None
