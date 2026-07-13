"""Headless Battleship tests: rules, AI plays a full game to a terminal state,
serialisation round-trip, and the board animation kit. No pygame, no GL.

Run: python tools/test_battleship.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.battleship.model import BattleshipModel, FLEET, OTHER  # noqa: E402
from games.battleship.ai import ai_fire  # noqa: E402
from games.board.anim import Anim, AnimQueue, ease_out  # noqa: E402


def test_placement():
    m = BattleshipModel(random.Random(1))
    assert m.place_ship("P1", "Destroyer", 2, 0, 0, True)
    assert not m.place_ship("P1", "Destroyer", 2, 0, 0, True), "overlap allowed"
    assert not m.place_ship("P1", "Carrier", 5, 8, 0, True), "off-board allowed"
    # a full random fleet: right count, in bounds, no overlaps
    for p in ("P1", "P2"):
        m.random_place(p)
        assert m.fleet_complete(p)
        occ = [tuple(c) for s in m.ships[p] for c in s["cells"]]
        assert len(occ) == len(set(occ)) == sum(sz for _, sz in FLEET)
        assert all(0 <= x < m.size and 0 <= y < m.size for x, y in occ)
    print("placement OK")


def test_fire_rules():
    m = BattleshipModel(random.Random(2))
    m.ships["P1"] = [{"name": "Destroyer", "size": 2, "cells": [[0, 0], [1, 0]]}]
    m.ships["P2"] = [{"name": "Destroyer", "size": 2, "cells": [[5, 5], [5, 6]]}]
    m.begin_fire("P1")
    assert m.fire("P2", 0, 0) is None, "fired out of turn"
    miss = m.fire("P1", 9, 9)
    assert miss and not miss["hit"] and m.turn == "P2", "miss should hand off"
    assert m.fire("P1", 0, 0) is None, "moved twice"
    m.fire("P2", 4, 4)  # P2 misses, back to P1
    hit = m.fire("P1", 5, 5)
    assert hit["hit"] and hit["sunk"] is None
    m.fire("P2", 4, 5)
    sunk = m.fire("P1", 5, 6)
    assert sunk["hit"] and sunk["sunk"] == "Destroyer" and sunk["win"] is True
    assert m.winner == "P1" and m.phase == "over"
    assert m.fire("P1", 1, 1) is None, "fired after game over"
    print("fire rules OK")


def _play_ai_game(seed):
    m = BattleshipModel(random.Random(seed))
    m.random_place("P1")
    m.random_place("P2")
    m.begin_fire("P1")
    moves = 0
    while m.winner is None:
        shooter = m.turn
        x, y = ai_fire(m)
        res = m.fire(shooter, x, y)
        assert res is not None, "AI produced an illegal shot"
        moves += 1
        assert moves <= 2 * m.size * m.size, "game did not terminate"
    return m, moves


def test_ai_full_game():
    m, moves = _play_ai_game(7)
    loser = OTHER[m.winner]
    assert m.all_sunk(loser) and not m.all_sunk(m.winner)
    # every fired cell is unique per target board (no wasted repeats)
    for p in ("P1", "P2"):
        fired = [tuple(c) for c in m.shots[p]]
        assert len(fired) == len(set(fired))
    # deterministic: same seed reproduces the same game exactly
    m2, moves2 = _play_ai_game(7)
    assert (m.winner, moves) == (m2.winner, moves2)
    print(f"AI full game OK (winner={m.winner}, {moves} shots, deterministic)")


def test_serialisation():
    m, _ = _play_ai_game(3)
    blob = json.dumps(m.to_state())          # must be JSON-serialisable
    back = BattleshipModel.from_state(json.loads(blob))
    assert back.to_state() == m.to_state()
    assert back.winner == m.winner and back.ships == m.ships
    print(f"serialisation OK ({len(blob)} bytes)")


def test_anim_kit():
    assert ease_out(0) == 0.0 and abs(ease_out(1) - 1.0) < 1e-9
    fired = []
    q = AnimQueue()
    q.add(Anim("a", 1.0, on_done=lambda a: fired.append("a")))
    q.add(Anim("b", 1.0, on_done=lambda a: fired.append("b")))
    assert q.busy and q.current.kind == "a"
    q.update(0.5)
    assert 0.0 < q.current.p < 1.0 and q.current.kind == "a"  # still on first
    q.update(0.6)                     # first completes -> pops
    assert q.current.kind == "b" and fired == ["a"]
    q.update(1.0)
    assert not q.busy and fired == ["a", "b"]  # on_done fires once each
    print("anim kit OK")


def main():
    test_placement()
    test_fire_rules()
    test_ai_full_game()
    test_serialisation()
    test_anim_kit()
    print("ALL BATTLESHIP TESTS PASSED")


if __name__ == "__main__":
    main()
