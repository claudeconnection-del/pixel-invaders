"""Tiny animation kit for board games — the spec makes elegant motion a
first-class concern, and the animation queue also *gates turn handoff*: a move
plays out fully (missile arc, splash, token hop) before the next turn begins,
and — online — before the move is pushed to the relay.

Pure/logic-only: no pygame, no GL. A game's view reads an Anim's eased
progress and draws accordingly.
"""


def ease_out(t):
    """Cubic ease-out: fast then settling. t in [0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return 4 * t * t * t if t < 0.5 else 1.0 - ((-2 * t + 2) ** 3) / 2


def lerp(a, b, t):
    return a + (b - a) * t


class Anim:
    """One timed animation. `kind`/`data` are opaque to the queue; the view
    interprets them. `on_done` (optional) fires once when it completes — used
    to apply a move's effect at the right beat (e.g. reveal a hit at impact)."""

    def __init__(self, kind, duration, data=None, ease=ease_out, on_done=None):
        self.kind = kind
        self.duration = max(1e-4, float(duration))
        self.data = data or {}
        self.ease = ease
        self.on_done = on_done
        self.elapsed = 0.0
        self._fired = False

    @property
    def t(self):
        """Raw linear progress in [0,1]."""
        return min(1.0, self.elapsed / self.duration)

    @property
    def p(self):
        """Eased progress in [0,1]."""
        return self.ease(self.t)

    @property
    def done(self):
        return self.elapsed >= self.duration

    def update(self, dt):
        self.elapsed += dt
        if self.done and not self._fired:
            self._fired = True
            if self.on_done:
                self.on_done(self)


class AnimQueue:
    """Sequential animation queue. `busy` gates input/turn handoff so a move
    fully resolves before the next begins."""

    def __init__(self):
        self._items = []

    def add(self, anim):
        self._items.append(anim)
        return anim

    def clear(self):
        self._items.clear()

    @property
    def busy(self):
        return bool(self._items)

    @property
    def current(self):
        return self._items[0] if self._items else None

    def update(self, dt):
        """Advance the head animation; pop it when done. One per frame keeps
        sequencing strict (missile lands, THEN the splash starts)."""
        if not self._items:
            return
        cur = self._items[0]
        cur.update(dt)
        if cur.done:
            self._items.pop(0)
