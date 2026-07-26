"""Battleship AI: the classic hunt/target heuristic.

Fair play — it only uses information a real opponent has: the results of its
own shots (hit / miss / sunk). It never reads un-fired ship locations. In
HUNT mode it fires on a checkerboard (no ship can hide from a parity sweep);
once it has an unsunk hit it switches to TARGET mode, firing adjacent cells and
extending along a proven line.
"""
from games.battleship.model import OTHER


def _live_hits(model, target):
    """Cells the AI has hit that belong to ships not yet sunk."""
    out = []
    for x, y in (tuple(s) for s in model.shots[target]):
        ship = model.ship_at(target, x, y)
        if ship is not None and not model.is_sunk(target, ship):
            out.append((x, y))
    return out


def ai_fire(model):
    """Pick (x, y) for the side whose turn it is to fire. Deterministic given
    model.rng. Assumes model.phase == 'fire'."""
    me = model.turn
    target = OTHER[me]
    size = model.size
    shot = {tuple(s) for s in model.shots[target]}

    def unshot(x, y):
        return 0 <= x < size and 0 <= y < size and (x, y) not in shot

    hits = _live_hits(model, target)
    candidates = []
    if hits:
        hset = set(hits)
        for (x, y) in hits:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not unshot(nx, ny):
                    continue
                # weight cells that continue an existing 2+ line of hits: if the
                # cell opposite this neighbour is also a hit, we're on the ship's
                # axis — prioritise finishing it
                weight = 3 if (x - dx, y - dy) in hset else 1
                candidates.extend([(nx, ny)] * weight)
    if not candidates:
        parity = [(x, y) for x in range(size) for y in range(size)
                  if unshot(x, y) and (x + y) % 2 == 0]
        candidates = parity or [(x, y) for x in range(size)
                                for y in range(size) if unshot(x, y)]
    return model.rng.choice(candidates)
