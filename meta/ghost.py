"""Ghost racing: record a run's trajectory, replay it as a translucent rival.

Games are deterministic, but a ghost doesn't re-simulate — it records a small
uniform-rate trajectory (a per-frame *sample* tuple the game knows how to
re-draw, plus the score at each tick) and the replayer interpolates it by
elapsed time. This is generic: any run that implements ghost_sample() gets
recorded, and any run that reads its per-frame ghost_state can draw the rival.

Ghosts live in their own ghosts.json (not the frequently-saved profile) so the
personal-best replay for each game+mode persists without bloating profile
writes. Kept small: capped sample count, rounded values.
"""
import copy
import json
import os
import tempfile

SAMPLE_DT = 0.05        # 20 Hz trajectory
MAX_SAMPLES = 1400      # ~70s at full rate; longer runs are downsampled
SCHEMA = 1


def default_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ghosts.json")


def board_key(game_id, mode):
    return f"{game_id}:{mode}"


class GhostRecorder:
    """Accumulates a uniform-dt trajectory over a run."""

    def __init__(self, sample_dt=SAMPLE_DT):
        self.dt = sample_dt
        self.samples = []   # list of tuples (game-defined arity)
        self.scores = []    # int score at each sample
        self._acc = sample_dt  # emit on the very first frame

    def on_frame(self, dt, run):
        self._acc += dt
        if self._acc < self.dt:
            return
        self._acc -= self.dt
        sample = run.ghost_sample()
        if sample is None:
            sample = self.samples[-1] if self.samples else (0.0, 0.0)
        self.samples.append(tuple(round(float(v), 1) for v in sample))
        self.scores.append(int(run.score))

    def build(self, game_id, mode, final_score):
        """Serialisable ghost, downsampled + rounded to stay small."""
        samples, scores, dt = self.samples, self.scores, self.dt
        if len(samples) > MAX_SAMPLES:
            step = len(samples) // MAX_SAMPLES + 1
            samples = samples[::step]
            scores = scores[::step]
            dt = self.dt * step
        return {
            "schema": SCHEMA, "game": game_id, "mode": mode,
            "score": int(final_score), "dt": dt,
            "samples": [list(s) for s in samples], "scores": scores,
        }


class GhostPlayer:
    """Interpolates a recorded ghost by elapsed run time."""

    def __init__(self, ghost):
        self.dt = ghost["dt"]
        self.samples = ghost["samples"]
        self.scores = ghost["scores"]
        self.score = int(ghost.get("score", 0))
        self.duration = self.dt * max(0, len(self.samples) - 1)

    @property
    def valid(self):
        return len(self.samples) >= 2

    def sample_at(self, t):
        """Linear-interpolated trajectory tuple at elapsed time t (clamped)."""
        if not self.samples:
            return None
        f = t / self.dt
        i = int(f)
        if i >= len(self.samples) - 1:
            return tuple(self.samples[-1])
        frac = f - i
        a, b = self.samples[i], self.samples[i + 1]
        return tuple(av + (bv - av) * frac for av, bv in zip(a, b))

    def score_at(self, t):
        if not self.scores:
            return 0
        i = min(int(t / self.dt), len(self.scores) - 1)
        return self.scores[i]

    def finished(self, t):
        return t >= self.duration


# ------------------------------------------------------------- persistence
def load(path=None):
    path = path or default_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save(store, path=None):
    path = path or default_path()
    directory = os.path.dirname(path) or "."
    try:
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f)
        os.replace(tmp, path)
    except OSError:
        pass


def get_ghost(store, game_id, mode):
    return store.get(board_key(game_id, mode))


def maybe_store_best(store, ghost, path=None):
    """Store this ghost as the personal best for its game+mode if it beats
    the one already there. Returns True if stored."""
    key = board_key(ghost["game"], ghost["mode"])
    prev = store.get(key)
    if prev is not None and prev.get("score", 0) >= ghost["score"]:
        return False
    store[key] = copy.deepcopy(ghost)
    save(store, path)
    return True
