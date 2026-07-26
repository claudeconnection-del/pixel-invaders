"""Cabinet Man's pilot for Voxel Serpent: "draws odd symbols, never in danger."

The house plays the snake flawlessly -- but between feeding runs it traces
deliberate glyphs with its body (a box, a zig-zag, a spiral) that a watcher
notices and double-takes at. Competence plus strangeness, always both.

Safety comes first and is never negotiable. The naive "is the next cell free"
check isn't enough -- a snake can walk into a pocket that's momentarily open
but seals it into a space too small to survive. The real invariant, the one
every serious snake AI uses, is *tail reachability*: after a candidate move,
can the head still reach its own tail through free cells? The tail vacates one
cell every step, so as long as a path to it exists the snake can always follow
its own tail forever and never trap itself. `_move_is_safe` simulates the move
(mirroring the world's exact grow/tail-pop timing) and BFS-floods from the new
head; the move is safe iff the new tail is reachable. Every move the pilot ever
makes -- food pathing OR glyph tracing -- must pass this check, so the "never
in danger" half of the brief is a hard guarantee, not a hope.

Given that floor, each step the pilot picks a direction by priority:

  1. **Glyph mode** (the personality): when the board is comfortable (snake
     short enough that it isn't crowding itself, and no fruit is going stale),
     it follows a pre-chosen glyph -- a relative direction sequence from a
     small library (box, zig-zag, staircase, comb) traced in open space.
     Every glyph step is still gated by `_move_is_safe`; the instant the next
     glyph move would be unsafe (or the board stops being comfortable) the
     glyph is abandoned and control falls to food pathing. Which glyph, and
     where it starts, is drawn from a Random seeded off the run's own rng --
     deterministic, no wall-clock rolls, so a piloted run reproduces exactly
     from its seed like everything else in this cabinet.
  2. **Food pathing**: a BFS over free cells from the head to the fruit gives
     the shortest safe route; the pilot takes its first step -- but only if
     that step also passes `_move_is_safe` (a shortest path can still walk
     into a trap, so the tail check overrides the path). If the fruit is
     unreachable right now, it stalls safely instead (see 3).
  3. **Stall / endgame**: with no safe food step, the pilot follows its own
     tail (always the safest possible move -- chase the one cell guaranteed to
     be empty next step), which both survives crowded boards and naturally
     produces the space-filling serpentine of a dominating snake. If even that
     has no safe option, it takes whichever legal move leaves the largest
     reachable free area and accepts that a truly sealed board ends the run --
     "losing weirdly is on-brand," and a v1 snake can't always escape a board
     the obstacle spawns have genuinely walled off.

No shooting here (Serpent has none); the pilot only ever emits one direction
bit per frame. The world only turns on its own step timer, so returning the
same intended direction every frame until the snake actually moves is correct
and idempotent.
"""
import random
from collections import deque

from game.entities import InputState
from games.serpent.world import COLS, ROWS, DIRS, OPPOSITE

# Board is comfortable enough to indulge a glyph while the snake is shorter
# than this (it isn't yet crowding itself) and the current fruit hasn't been
# sitting unclaimed for too many of the pilot's own steps.
_GLYPH_MAX_LENGTH = 18
_FRUIT_PATIENCE = 26          # steps a fruit may age before food pathing wins
_GLYPH_COOLDOWN = 6           # steps between finishing one glyph and the next

# Glyph library: each is a sequence of absolute directions traced in open
# space. Kept small and boxy so they read as deliberate shapes at a glance.
_GLYPHS = {
    "box": ["right", "right", "down", "down", "left", "left", "up", "up"],
    "zigzag": ["right", "down", "right", "up", "right", "down", "right", "up"],
    "staircase": ["right", "down", "right", "down", "left", "up", "left", "up"],
    "comb": ["down", "right", "up", "right", "down", "right", "up", "right"],
}
_GLYPH_NAMES = sorted(_GLYPHS)


def _in_bounds(cell):
    return 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS


def _step_cell(cell, direction):
    dx, dy = DIRS[direction]
    return (cell[0] + dx, cell[1] + dy)


def _next_body(body, new_head, grow):
    """The body after moving the head to `new_head`, mirroring the world's
    grow/tail-pop timing: the tail only stays put while `grow > 0`."""
    nb = [new_head]
    nb.extend(body)
    if grow == 0:
        nb.pop()
    return nb


def _reachable(head, tail, blocked):
    """BFS from `head` over in-bounds, non-`blocked` cells; True if `tail` is
    reached. `tail` itself is treated as passable (it vacates next step)."""
    if head == tail:
        return True
    seen = {head}
    q = deque([head])
    while q:
        cur = q.popleft()
        for d in DIRS:
            nxt = _step_cell(cur, d)
            if nxt == tail:
                return True
            if not _in_bounds(nxt) or nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    return False


def _reachable_area(head, blocked):
    """How many free cells the head can reach (flood-fill size) -- the
    fallback tiebreaker when no move can reach the tail."""
    seen = {head}
    q = deque([head])
    while q:
        cur = q.popleft()
        for d in DIRS:
            nxt = _step_cell(cur, d)
            if not _in_bounds(nxt) or nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    return len(seen)


def legal_directions(world):
    """Directions the snake may turn (everything but a straight reversal),
    matching the world's own `apply_input` rule."""
    return [d for d in DIRS if d != OPPOSITE[world.direction]]


def move_is_safe(world, direction):
    """True if turning `direction` this step both survives the immediate
    collision check AND leaves the head able to reach its own tail afterward
    (the tail-reachability invariant). Pure -- reads the world, mutates
    nothing."""
    nh = _step_cell(world.body[0], direction)
    if not _in_bounds(nh) or nh in world.obstacles:
        return False
    tail_moving = world.grow == 0
    body_check = world.body[:-1] if tail_moving else world.body
    if nh in body_check:
        return False
    nb = _next_body(world.body, nh, world.grow)
    blocked = set(nb[1:-1]) | world.obstacles     # head is start, tail is goal
    return _reachable(nh, nb[-1], blocked)


def _bfs_path_dir(world, goal):
    """First direction of a shortest free-cell path from the head to `goal`,
    or None if `goal` is unreachable. Obstacles + the snake's own body (minus
    the tail, which vacates) block the path."""
    head = world.body[0]
    if head == goal:
        return None
    blocked = set(world.body[:-1]) | world.obstacles
    seen = {head}
    q = deque([(head, None)])
    while q:
        cur, first = q.popleft()
        for d in legal_directions(world) if cur == head else DIRS:
            nxt = _step_cell(cur, d)
            step_first = d if cur == head else first
            if nxt == goal:
                return step_first
            if not _in_bounds(nxt) or nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append((nxt, step_first))
    return None


class SerpentPilot:
    """Cabinet Man at the snake: see module docstring."""

    label = "Cabinet Man"

    def __init__(self, run):
        # deterministic, seeded off the run's own rng (no wall-clock rolls)
        self.rng = random.Random(run.world.rng.random())
        self._glyph = None          # list of remaining directions, or None
        self._glyph_cooldown = 0
        self._fruit_age = 0
        self._last_fruit = run.world.fruit
        self.glyph_moves = 0        # count of glyph waypoints actually executed
        self._last_len = run.world.length

    def step(self, run, dt):
        world = run.world
        inp = InputState()
        if world.run_over:
            return inp

        self._track_progress(world)
        direction = self._choose(world)
        if direction is not None:
            setattr(inp, direction, True)
        return inp

    # ------------------------------------------------------------- internals
    def _track_progress(self, world):
        """Age the current fruit (per snake move, detected by length or fruit
        identity changing) so a stale fruit eventually outranks glyph play."""
        moved = world.length != self._last_len or world.fruit != self._last_fruit
        if world.fruit != self._last_fruit:
            self._fruit_age = 0
            self._last_fruit = world.fruit
        elif moved:
            self._fruit_age += 1
        self._last_len = world.length

    def _comfortable(self, world):
        return (world.length < _GLYPH_MAX_LENGTH
                and self._fruit_age < _FRUIT_PATIENCE)

    def _choose(self, world):
        # 1. glyph mode (only while comfortable)
        if self._comfortable(world):
            d = self._glyph_direction(world)
            if d is not None:
                return d
        else:
            self._glyph = None      # drop any glyph the moment we're crowded

        # 2. food pathing (safe first step toward the fruit)
        if world.fruit is not None:
            d = _bfs_path_dir(world, world.fruit)
            if d is not None and move_is_safe(world, d):
                return d

        # 3. stall: follow the tail (the guaranteed-empty cell), else the
        #    safe move leaving the most room, else the least-bad legal move.
        return self._safe_fallback(world)

    def _glyph_direction(self, world):
        """The next safe direction of the active glyph, starting a new one if
        idle and off cooldown. Returns None to defer to food pathing."""
        if self._glyph is None:
            if self._glyph_cooldown > 0:
                self._glyph_cooldown -= 1
                return None
            name = _GLYPH_NAMES[self.rng.randrange(len(_GLYPH_NAMES))]
            self._glyph = list(_GLYPHS[name])
        # skip glyph steps that are illegal (reversal) or unsafe; if the whole
        # remaining glyph is unusable from here, abandon it
        while self._glyph:
            d = self._glyph[0]
            if d != OPPOSITE[world.direction] and move_is_safe(world, d):
                self._glyph.pop(0)
                self.glyph_moves += 1
                if not self._glyph:
                    self._glyph_cooldown = _GLYPH_COOLDOWN
                return d
            self._glyph.pop(0)
        self._glyph = None
        self._glyph_cooldown = _GLYPH_COOLDOWN
        return None

    def _safe_fallback(self, world):
        tail = world.body[-1]
        options = [d for d in legal_directions(world) if move_is_safe(world, d)]
        if options:
            # prefer heading toward the tail (keeps the escape route open),
            # else the move opening the most reachable space
            for d in options:
                if _step_cell(world.body[0], d) == tail:
                    return d
            return max(options, key=lambda d: self._area_after(world, d))
        # no safe move: take any legal non-fatal move, largest area; if even
        # that's impossible the board is sealed and the run ends (on-brand).
        legal = [d for d in legal_directions(world)
                 if self._survives_immediate(world, d)]
        if legal:
            return max(legal, key=lambda d: self._area_after(world, d))
        return legal_directions(world)[0]      # doomed -- move anyway

    def _survives_immediate(self, world, direction):
        nh = _step_cell(world.body[0], direction)
        if not _in_bounds(nh) or nh in world.obstacles:
            return False
        tail_moving = world.grow == 0
        body_check = world.body[:-1] if tail_moving else world.body
        return nh not in body_check

    def _area_after(self, world, direction):
        nh = _step_cell(world.body[0], direction)
        nb = _next_body(world.body, nh, world.grow)
        blocked = set(nb[1:-1]) | world.obstacles
        return _reachable_area(nh, blocked)


def create_pilot(run):
    return SerpentPilot(run)
