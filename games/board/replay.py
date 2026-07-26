"""Board-move replays with per-perspective playback.

A turn-based match is recorded as seed + fleet placements + the ordered move
stream. Because the model separates truth from view, playback can be projected
through ANY seat's `secret_view` — so you can re-watch the match exactly as one
player saw it at each moment (their own fleet visible, the opponent's un-hit
ships still hidden), or flip to an omniscient DIRECTOR view that reveals both
fleets.

This is deliberately distinct from meta/replay.py (which records per-frame
input bitmasks for the real-time games and plays back by re-feeding inputs);
board replays re-apply *moves* to the model. The in-engine replay browser for
the real-time games ignores these via the "kind" field.
"""
import json
import os
import random
import time

from games.battleship.model import BattleshipModel

SCHEMA = 1
REPLAY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "replays")


class BoardReplayRecorder:
    """Accumulates a match as placements + an ordered move stream."""

    def __init__(self, game_id, mode, seed=0):
        self.game = game_id
        self.mode = mode
        self.seed = int(seed)
        self.placements = {}     # seat -> [ {name,size,x,y,horizontal}, ... ]
        self.moves = []          # [ {seat,x,y}, ... ] in play order

    def placement(self, seat, layout):
        self.placements[seat] = [dict(s) for s in (layout or [])]

    def move(self, seat, x, y):
        self.moves.append({"seat": seat, "x": int(x), "y": int(y)})

    def build(self, winner):
        return {
            "schema": SCHEMA, "kind": "board", "game": self.game,
            "mode": self.mode, "seed": self.seed,
            "placements": self.placements, "moves": self.moves,
            "winner": winner, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }


class BoardReplay:
    """Deterministic playback of a recorded board match, projectable through a
    chosen perspective ("P1", "P2", or "director")."""

    def __init__(self, data):
        self.game = data["game"]
        self.mode = data["mode"]
        self.seed = int(data.get("seed", 0))
        self.placements = data["placements"]
        self.moves = data["moves"]
        self.winner = data.get("winner")

    @property
    def total(self):
        return len(self.moves)

    def rebuild_to(self, step):
        """A fresh model with the fleets placed and the first `step` moves
        applied. Pure and deterministic (placements + moves are explicit)."""
        m = BattleshipModel(random.Random(self.seed))
        for seat, layout in self.placements.items():
            m.ships[seat] = []
            for s in layout:
                m.place_ship(seat, s["name"], int(s["size"]), int(s["x"]),
                             int(s["y"]), bool(s["horizontal"]))
        m.begin_fire("P1")
        for mv in self.moves[:max(0, min(step, self.total))]:
            m.fire(mv["seat"], mv["x"], mv["y"])
        return m

    def view(self, step, perspective):
        """The projected view at `step` for the chosen perspective. "P1"/"P2"
        get that seat's secret_view (opponent's hidden ships stay hidden);
        "director" gets an omniscient view revealing both fleets."""
        from games.battleship import game as bs
        m = self.rebuild_to(step)
        if perspective in ("P1", "P2"):
            return bs.secret_view(m, perspective)
        return director_view(m)


def director_view(model):
    """Omniscient post-match view: the public board plus BOTH full fleets.
    Only for replays/spectating — never sent to a live player."""
    from games.battleship import game as bs
    view = bs.public_view(model)
    view["perspective"] = "director"
    view["fleets"] = {
        p: [{"cells": [list(c) for c in s["cells"]],
             "sunk": model.is_sunk(p, s)} for s in model.ships[p]]
        for p in model.ships
    }
    return view


# ------------------------------------------------------------- persistence
def save(data):
    """Persist as the 'last board match' for this game+mode, atomically."""
    os.makedirs(REPLAY_DIR, exist_ok=True)
    path = os.path.join(REPLAY_DIR, f"last_{data['game']}_{data['mode']}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return path


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
