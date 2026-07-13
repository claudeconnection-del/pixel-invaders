"""Run replays: a deterministic recording of a run as its seed + input
stream. Because every game is a pure seeded simulation, re-feeding the same
seed and per-frame inputs reconstructs the run exactly — so a replay is a
few KB (not a video), can be re-rendered at any resolution/framerate on
demand, watched later, or exported to GIF/MP4 client-side (tools/export_replay).

Compact format: booleans packed into one bitmask per frame; the analog fields
(mouse aim, strafe, look) are only stored for games that use them (the FPS /
aim games), so field-game replays are ~one int per frame.
"""
import json
import os
import tempfile
import time

from game.entities import InputState

SCHEMA = 1
REPLAY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "replays")

_BITS = (("left", 1), ("right", 2), ("up", 4), ("down", 8),
         ("focus", 16), ("fire", 32))


class ReplayRecorder:
    def __init__(self, game_id, mode, seed, analog):
        self.game = game_id
        self.mode = mode
        self.seed = int(seed)
        self.analog = bool(analog)
        # exact per-frame dt is required for deterministic reconstruction
        # (the sim is a pure function of seed + dt-stream + inputs); rounding
        # dt drifts the timeline and desyncs. Stored as full-precision floats.
        self.dts = []
        self.masks = []
        self.analog_data = []

    def on_frame(self, dt, inp):
        self.dts.append(float(dt))
        m = 0
        for name, bit in _BITS:
            if getattr(inp, name):
                m |= bit
        self.masks.append(m)
        if self.analog:
            self.analog_data.append([
                float(inp.aim_x), float(inp.aim_y), float(inp.strafe),
                float(inp.turn), float(inp.look_dx)])

    @property
    def frame_count(self):
        return len(self.dts)

    def build(self, score=0):
        return {
            "schema": SCHEMA, "game": self.game, "mode": self.mode,
            "seed": self.seed, "analog": self.analog, "score": int(score),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "dts": self.dts, "masks": self.masks,
            "analog_data": self.analog_data,
        }


class Replay:
    """Iterable playback of a recorded replay."""

    def __init__(self, data):
        self.game = data["game"]
        self.mode = data["mode"]
        self.seed = int(data["seed"])
        self.analog = bool(data.get("analog"))
        self.score = int(data.get("score", 0))
        self.dts = data["dts"]
        self.masks = data["masks"]
        self.analog_data = data.get("analog_data", [])

    @property
    def frame_count(self):
        return len(self.dts)

    @property
    def duration(self):
        return sum(self.dts)

    def frames(self):
        for i in range(len(self.dts)):
            dt = self.dts[i]
            m = self.masks[i]
            inp = InputState(
                left=bool(m & 1), right=bool(m & 2), up=bool(m & 4),
                down=bool(m & 8), focus=bool(m & 16), fire=bool(m & 32))
            if self.analog and i < len(self.analog_data):
                ax, ay, sx, tn, lk = self.analog_data[i]
                inp.aim_x, inp.aim_y = ax, ay
                inp.strafe, inp.turn, inp.look_dx = sx, tn, lk
            yield dt, inp


# ------------------------------------------------------------- persistence
def _atomic_write(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def last_path(game_id, mode):
    return os.path.join(REPLAY_DIR, f"last_{game_id}_{mode}.json")


def save_last(data):
    """Overwrite the 'last run' replay for this game+mode (always kept so a
    run can be exported after the fact)."""
    path = last_path(data["game"], data["mode"])
    _atomic_write(path, data)
    return path


def keep(data):
    """Save a timestamped keeper copy (a run the player wants to hold onto)."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"{data['game']}_{data['mode']}_{data.get('score', 0):07d}_{ts}.json"
    path = os.path.join(REPLAY_DIR, name)
    _atomic_write(path, data)
    return path
