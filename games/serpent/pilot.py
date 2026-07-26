"""Cabinet Man's reference pilot for Voxel Serpent: "draws odd symbols, never
in danger." The snake never makes a move that could seal off its own escape:
every candidate is checked for a standing path back to its own tail (with a
few extra guards — see `_move_is_safe`/`_safest_direction` — against the
specific ways a pure flood-fill/tail-chase check can still be fooled), a
real generalisation of the attract-mode bot's 1-step lookahead
(`games/serpent/bot.py`) that catches multi-step traps a greedy bot would
happily crawl into. Fed and safe, it doesn't just beeline for fruit: between
food runs it deliberately traces glyphs (a spiral, a zigzag, a box-wave, a
couple of letterforms, a heart) with its own body, picked deterministically
from the run's rng — a watcher doing a double-take is the point. The instant
a glyph waypoint would break the safety invariant, it's abandoned mid-shape
and the snake falls back to food-pathing, no drama. Once the snake dominates
the board there's no more room for tricks: it drops the glyph library for an
honest space-filling serpentine sweep and rides the safety check to the
highest length the board allows before the inevitable.

This is a strong heuristic, not a formally-verified solver: Serpent's
obstacle walls accumulate permanently (never removed) on a fixed 15x16
field, so no bounded-lookahead pilot survives forever — the board eventually
wins. It is tested to reliably clear a solid length on a range of seeds,
well past the point a naive 1-step-lookahead bot would already be dead.

Deterministic from the run's own rng (`run.world.rng`) — no wall-clock
randomness — so a pilot run is exactly reproducible from the run's seed.
"""
from collections import deque

from game.entities import InputState
from games.serpent.world import COLS, DIRS, OPPOSITE, ROWS

_NEIGHBOR_DELTAS = ((0, -1), (0, 1), (-1, 0), (1, 0))

# ----------------------------------------------------------------- glyphs
# Each glyph is a small library of *sparse* waypoints (local coordinates,
# origin top-left) that the pilot paths between with the same safety-checked
# BFS used for food. Placement is centred on the board deterministically (no
# rng spent on position); only *which* glyph gets drawn is rng-chosen.
_GLYPHS = {
    # concentric squares shrinking to a point — reads as a spiral/target
    "spiral": [(0, 0), (8, 0), (8, 8), (0, 8),
               (2, 2), (6, 2), (6, 6), (2, 6), (4, 4)],
    # a hard zigzag, corner to corner
    "zigzag": [(6, 0), (0, 0), (0, 4), (6, 4), (6, 8), (0, 8)],
    # a square wave: flat top, flat bottom, alternating
    "box_wave": [(0, 0), (0, 4), (3, 4), (3, 0), (6, 0), (6, 4), (9, 4), (9, 0)],
    # letterform: V
    "letter_v": [(0, 0), (4, 8), (8, 0)],
    # letterform: W
    "letter_w": [(0, 0), (2, 8), (4, 2), (6, 8), (8, 0)],
    # a stylised pixel heart outline
    "heart": [(5, 8), (1, 4), (1, 1), (3, 0), (5, 2), (7, 0), (9, 1), (9, 4), (5, 8)],
}

GLYPH_NAMES = tuple(sorted(_GLYPHS))


def _glyph_cells(name, cols, rows, margin=2):
    """Translate a glyph's local waypoints into absolute board cells,
    centred with `margin` cells of clearance from every wall. Returns None
    if it can't fit (shouldn't happen on Serpent's 15x16 field for any glyph
    in the library, but a pilot should never crash over a decoration)."""
    pts = _GLYPHS[name]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w, h = maxx - minx, maxy - miny
    max_ox = cols - 1 - margin - w
    max_oy = rows - 1 - margin - h
    if max_ox < margin or max_oy < margin:
        return None
    ox = margin + (max_ox - margin) // 2
    oy = margin + (max_oy - margin) // 2
    return [(ox + (x - minx), oy + (y - miny)) for x, y in pts]


# ------------------------------------------------------------------ search
def _bfs_path(start, goal, blocked, cols, rows):
    """Shortest path start -> goal over the open grid (4-connected), treating
    cells in `blocked` as walls (the goal cell itself is always enterable
    even if flagged blocked, e.g. a body cell that will have vacated by the
    time we'd reach it). Returns the cell list including both ends, or None
    if unreachable."""
    if start == goal:
        return [start]
    prev = {start: None}
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        if cur == goal:
            break
        x, y = cur
        for dx, dy in _NEIGHBOR_DELTAS:
            nxt = (x + dx, y + dy)
            if nxt in prev or not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            if nxt in blocked and nxt != goal:
                continue
            prev[nxt] = cur
            dq.append(nxt)
    if goal not in prev:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def _flood_fill_count(blocked, start, cols, rows, limit):
    """Size of the open region reachable from `start` (inclusive), stopping
    early once it reaches `limit` — we only ever need to know whether it
    clears a threshold, not the exact number."""
    if not (0 <= start[0] < cols and 0 <= start[1] < rows) or start in blocked:
        return 0
    seen = {start}
    dq = deque([start])
    count = 0
    while dq:
        cur = dq.popleft()
        count += 1
        if count >= limit:
            return count
        x, y = cur
        for dx, dy in _NEIGHBOR_DELTAS:
            nxt = (x + dx, y + dy)
            if nxt in seen or nxt in blocked or not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            seen.add(nxt)
            dq.append(nxt)
    return count


def _completes_seal(body_after, obstacles, cols, rows):
    """True if occupying `body_after` (+ `obstacles`) fully blocks an entire
    board column or row. On a grid this small, a solid column/row is a hard
    topological wall — it permanently splits the board in two. A pure
    flood-fill/tail-chase safety check can't see this coming: each single
    step that extends such a wall still leaves plenty of "safe", tail-
    reachable open space *on the near side*, right up until the line
    completes and the far side (wherever the food happens to be) is sealed
    off for good, safe forever but unfed. This is checked as an explicit
    veto everywhere a move is judged safe."""
    occ = set(body_after)
    occ.update(obstacles)
    for x in range(cols):
        if all((x, y) in occ for y in range(rows)):
            return True
    for y in range(rows):
        if all((x, y) in occ for x in range(cols)):
            return True
    return False


def _direction_between(a, b):
    delta = (b[0] - a[0], b[1] - a[1])
    for name, d in DIRS.items():
        if d == delta:
            return name
    return None


# -------------------------------------------------------------- the pilot
class SerpentPilot:
    label = "Cabinet Man"

    # below this length, glyph episodes are allowed between food runs
    GLYPH_MAX_LENGTH = 40
    # at/above this length the board is "dominated" -> drop glyphs, fill safely
    ENDGAME_LENGTH = 130
    # odds of starting a glyph right after a fruit (vs. beelining for the next)
    GLYPH_CHANCE = 0.65

    def __init__(self, run):
        world = run.world
        self.rng = world.rng
        self.mode = "food"                    # "food" | "glyph" | "endgame"
        self._last_head = world.body[0]
        self._last_fruits_eaten = world.fruits_eaten
        self._glyph_name = None
        self._glyph_cells = []
        self._glyph_idx = 0
        self._cached_direction = None     # recomputed once per grid-step, not per frame
        # telemetry (also handy for tests): what the pilot actually did
        self.glyph_waypoints_hit = 0
        self.glyphs_started = []
        self.glyphs_completed = []
        self.glyphs_aborted = 0

    # ------------------------------------------------------------ contract
    def step(self, run, dt):
        world = run.world
        head = world.body[0]
        if head != self._last_head:
            self._on_arrive(world, head)
            self._last_head = head
            self._cached_direction = None
        if self._cached_direction is None:
            # the world only actually advances once every few frames (see
            # SerpentWorld._step_interval); re-deciding every single frame in
            # between would be wasted, identical work, so cache the choice
            # until the snake actually moves again.
            self._cached_direction = self._decide(world)
        direction = self._cached_direction
        if direction is None:
            return InputState()
        return InputState(**{direction: True})

    # --------------------------------------------------------- state machine
    def _on_arrive(self, world, head):
        ate = world.fruits_eaten != self._last_fruits_eaten
        self._last_fruits_eaten = world.fruits_eaten
        if self.mode == "glyph" and self._glyph_cells:
            target = self._glyph_cells[self._glyph_idx]
            if head == target:
                self.glyph_waypoints_hit += 1
                self._glyph_idx += 1
                if self._glyph_idx >= len(self._glyph_cells):
                    self._finish_glyph()
        if self.mode == "food" and ate:
            self._maybe_start_glyph(world)

    def _finish_glyph(self):
        self.glyphs_completed.append(self._glyph_name)
        self._glyph_name = None
        self._glyph_cells = []
        self._glyph_idx = 0
        self.mode = "food"

    def _abort_glyph(self):
        self.glyphs_aborted += 1
        self._glyph_name = None
        self._glyph_cells = []
        self._glyph_idx = 0
        self.mode = "food"

    def _maybe_start_glyph(self, world):
        if world.length >= self.ENDGAME_LENGTH or world.length >= self.GLYPH_MAX_LENGTH:
            return
        if self.rng.random() >= self.GLYPH_CHANCE:
            return
        name = self.rng.choice(GLYPH_NAMES)
        cells = _glyph_cells(name, COLS, ROWS)
        if not cells:
            return
        self._glyph_name = name
        self._glyph_cells = cells
        self._glyph_idx = 0
        self.mode = "glyph"
        self.glyphs_started.append(name)

    # -------------------------------------------------------------- decide
    def _decide(self, world):
        if world.length >= self.ENDGAME_LENGTH:
            if self.mode == "glyph":
                self._abort_glyph()
            self.mode = "endgame"

        if self.mode == "glyph":
            goal = self._glyph_cells[self._glyph_idx]
            direction, on_track = self._towards(world, goal)
            if not on_track:
                self._abort_glyph()
                direction, _ = self._towards(world, world.fruit)
            return direction

        if self.mode == "endgame":
            goal = self._sweep_target(world)
            direction, _on_track = self._towards(world, goal)
            return direction

        # default: food
        return self._towards(world, world.fruit)[0]

    # ---------------------------------------------------------- primitives
    def _towards(self, world, goal):
        """Best direction toward `goal`, safety-checked. Tier 1: shortest
        safe path straight there. Tier 2 (`_safest_direction`): no safe path
        exists — `goal` can be genuinely unreachable, e.g. the snake's own
        body has walled off a region — so fall back to whichever tail-safe
        move most reduces raw distance to `goal`, keeping the snake pressed
        toward the food's side of the board (and so toward wherever a gap
        will next open) instead of a plain "maximise open space" fallback,
        which can settle into a closed loop that's safe forever but never
        reaches food again.

        Returns (direction, on_track); on_track is True only for tier 1 — a
        real, direct, safe advance toward `goal` — glyph/endgame callers
        treat False as "bail out back to food-pathing"."""
        head = world.body[0]
        if goal is not None:
            blocked = set(world.body[:-1]) | world.obstacles
            path = _bfs_path(head, goal, blocked, COLS, ROWS)
            if path and len(path) >= 2:
                d = _direction_between(head, path[1])
                if d is not None and self._direction_safe(world, d):
                    return d, True
        return self._safest_direction(world, goal), False

    def _candidate_moves(self, world):
        """(direction, new_head, body_after) for every move that isn't an
        instant collision (wall/obstacle/self), excluding a direct reversal."""
        head = world.body[0]
        tail_moving = world.grow == 0
        body_check = set(world.body[:-1]) if tail_moving else set(world.body)
        out = []
        for name, (dx, dy) in DIRS.items():
            if name == OPPOSITE.get(world.direction):
                continue
            new_head = (head[0] + dx, head[1] + dy)
            if not (0 <= new_head[0] < COLS and 0 <= new_head[1] < ROWS):
                continue
            if new_head in world.obstacles or new_head in body_check:
                continue
            if world.grow > 0:
                body_after = [new_head] + world.body
            else:
                body_after = [new_head] + world.body[:-1]
            out.append((name, new_head, body_after))
        return out

    def _direction_safe(self, world, direction):
        """The real safety invariant, after the move: not just "is there
        open space" (a raw flood-fill count is easy to fool — a wide-looking
        region can still be a corridor that seals shut once the body fills
        it in behind itself) but "can the snake still reach its own tail".
        A path to the tail is a standing escape route — the tail keeps
        vacating cells as the snake advances, so as long as it's reachable
        the snake can always retreat by chasing it. This is the standard
        stronger-than-1-step-lookahead snake safety check; the existing bot
        only asks "is the very next cell free", never whether committing to
        it paints the snake into a corner a dozen moves later."""
        for name, new_head, body_after in self._candidate_moves(world):
            if name == direction:
                return self._move_is_safe(new_head, body_after, world.obstacles,
                                           avoid_seal=self.mode != "endgame")
        return False

    @staticmethod
    def _move_is_safe(new_head, body_after, obstacles, avoid_seal=True):
        if avoid_seal and _completes_seal(body_after, obstacles, COLS, ROWS):
            return False
        tail = body_after[-1]
        if new_head == tail:
            return True                 # already adjacent to the vacating tail
        blocked = set(body_after[1:-1]) | obstacles   # body minus head & tail
        return _bfs_path(new_head, tail, blocked, COLS, ROWS) is not None

    def _safest_direction(self, world, goal=None):
        """No safe shortest-path move toward `goal` available: pick whichever
        non-fatal move keeps a path to the snake's own tail (see
        `_move_is_safe`), prefers *not* stepping into a corridor cell with no
        spare exit (a corner/1-wide-dead-end has zero slack the moment the
        one way in also becomes the only way out — the classic way a
        forced, reversal-banned walk paints itself in), and *then* most
        reduces raw distance to `goal` — distance beats flood-filled open
        space so the snake actively presses toward the goal instead of
        settling for whatever move maximises empty space (which is what
        quietly produces a self-sealing, food-avoiding loop: comfortable
        forever, never eating again). Open space is only the last tie-break.
        Used for food/glyph fallback and for the endgame sweep's override.
        If nothing keeps the tail reachable either, fall back to spare exits
        and raw open space, then to whatever doesn't die outright — the
        board's simply too far gone."""
        best = None
        avoid_seal = self.mode != "endgame"
        for name, new_head, body_after in self._candidate_moves(world):
            safe = self._move_is_safe(new_head, body_after, world.obstacles,
                                       avoid_seal=avoid_seal)
            blocked_around = set(body_after[1:]) | world.obstacles
            spare_exits = sum(
                1 for dx, dy in _NEIGHBOR_DELTAS
                if (new_head[0] + dx, new_head[1] + dy) not in blocked_around
                and 0 <= new_head[0] + dx < COLS and 0 <= new_head[1] + dy < ROWS
            )
            dist = 0
            if goal is not None:
                dist = abs(new_head[0] - goal[0]) + abs(new_head[1] - goal[1])
            reachable = _flood_fill_count(blocked_around, new_head, COLS, ROWS, COLS * ROWS)
            key = (safe, min(spare_exits, 2), -dist, reachable)
            if best is None or key > best[0]:
                best = (key, name)
        if best is None:
            return world.pending_direction  # truly cornered: nothing to do but continue
        return best[1]

    def _sweep_target(self, world):
        """Endgame: an honest space-filling serpentine (boustrophedon) sweep
        — not a guaranteed Hamiltonian cycle (obstacles can break one), but a
        real attempt to cover the board row by row rather than folding up and
        giving up. `_towards` still safety-checks every step of it and falls
        back to `_safest_direction` the instant the sweep would trap it."""
        x, y = world.body[0]
        even_row = y % 2 == 0
        if even_row:
            if x < COLS - 1:
                return (x + 1, y)
            return (x, y + 1) if y < ROWS - 1 else (x - 1, y)
        else:
            if x > 0:
                return (x - 1, y)
            return (x, y + 1) if y < ROWS - 1 else (x + 1, y)


def create_pilot(run):
    return SerpentPilot(run)
