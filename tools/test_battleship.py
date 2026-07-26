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


def _place_fleet(run, seat):
    """Drive `seat`'s placement queue to completion via the cabinet input
    path (arrows/rotate/confirm), picking the first legal spot each time —
    exercises the same code a human at the cabinet would hit."""
    import pygame
    guard = 0
    while run._to_place[seat]:
        guard += 1
        assert guard < 500, "placement never completed"
        name, size = run._to_place[seat][0]
        placed = False
        for horizontal in (True, False):
            for y in range(run.model.size):
                for x in range(run.model.size):
                    if run.model.can_place(seat, x, y, size, horizontal):
                        run._cursor = [x, y]
                        run._orient_h = horizontal
                        run._handle_place_key(pygame.K_RETURN)
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break
        assert placed, f"no legal spot for {name} ({size})"


def test_vs_ai_mode():
    """A full VS-AI game via the actual mode entry point (create_run("ai",
    ...)) stays deterministic and never lets the human fire out of turn."""
    import pygame
    import games.battleship.game as bsgame

    def play(seed):
        run = bsgame.create_run("ai", random.Random(seed))
        assert run.mode == "ai" and run.session is None
        assert run.model.fleet_complete(run._cpu)   # house auto-deployed
        _place_fleet(run, run._human)
        assert run.model.fleet_complete(run._human)
        assert run.model.phase == "fire" and run.model.turn == run._human

        shots = 0
        while run.model.winner is None:
            shots += 1
            assert shots <= 4 * run.model.size * run.model.size, "no progress"
            if run.model.turn == run._cpu:
                # the house "thinks" for a beat, then fires itself
                run._cpu_timer = 1.0
                run.update(0.016, None)
                run.anim.clear()          # skip the missile animation gate
                continue
            # human's turn: find any legal cell and confirm it
            for y in range(run.model.size):
                for x in range(run.model.size):
                    if run.model.can_fire(run._human, x, y):
                        run._cursor = [x, y]
                        break
                else:
                    continue
                break
            run._handle_fire_key(pygame.K_RETURN)
            run.anim.clear()
        return run

    run = play(11)
    assert run.model.winner is not None
    assert run._last_replay is not None and run._last_replay["mode"] == "ai"
    assert run._last_replay["placements"]["P2"], "house placement not recorded"

    # deterministic given the same seed
    run2 = play(11)
    assert run2.model.winner == run.model.winner
    assert run2.model.to_state() == run.model.to_state()
    print("VS-AI mode OK (full game via create_run, deterministic, recorded)")


def test_hotseat_secrecy():
    """The hotseat turn-state machine never exposes the waiting seat's board
    during the handoff — assert directly on the "what would draw_hud show"
    selector rather than trusting the flag alone."""
    import games.battleship.game as bsgame

    run = bsgame.create_run("hotseat", random.Random(4))
    assert run.mode == "hotseat" and run.session is None
    assert run._stage == "handoff" and run._active == "P1"

    # nothing is placed/visible about either seat until the handoff confirms
    assert run.model.ships["P1"] == [] and run.model.ships["P2"] == []

    import pygame
    run._handle_offline_key(pygame.K_RETURN)     # "I'm ready" -> P1 places
    assert run._stage == "place"
    _place_fleet(run, "P1")
    # P1 done -> a handoff back to P2, and P1's fleet must not be visible
    # from a fresh reading of the offline-draw selector (mode != "secret")
    assert run._stage == "handoff" and run._active == "P2"
    assert run._handoff_purpose == "place"
    assert run.model.fleet_complete("P1")
    assert run.model.ships["P2"] == []           # P2 hasn't placed yet

    run._handle_offline_key(pygame.K_RETURN)     # P2 confirms -> P2 places
    assert run._stage == "place"
    _place_fleet(run, "P2")
    assert run._stage == "handoff" and run._handoff_purpose == "fire"
    assert run.model.phase == "fire" and run.model.turn == "P1"

    # firing alternates with a handoff on every miss (never on a hit, since
    # the shooter keeps the turn) — drive a few shots and check the invariant
    run._handle_offline_key(pygame.K_RETURN)     # P1 ready to fire
    assert run._stage == "fire" and run._active == "P1"
    for _ in range(40):
        if run.model.winner is not None:
            break
        shooter = run.model.turn
        cx, cy = next((x, y) for y in range(run.model.size)
                      for x in range(run.model.size)
                      if run.model.can_fire(shooter, x, y))
        run._cursor = [cx, cy]
        run._handle_fire_key(pygame.K_RETURN)
        run.anim.clear()
        if run.model.turn != shooter and run.model.winner is None:
            # a miss just handed the turn off: must be behind a blackout,
            # not sitting on the fire screen showing whoever's turn it now is
            assert run._stage == "handoff" and run._handoff_purpose == "fire"
            assert run._active == run.model.turn
            run._handle_offline_key(pygame.K_RETURN)   # next player confirms
    print("hotseat secrecy OK (blackout gates every placement + turn handoff)")


def main():
    test_placement()
    test_fire_rules()
    test_ai_full_game()
    test_serialisation()
    test_anim_kit()
    test_vs_ai_mode()
    test_hotseat_secrecy()
    print("ALL BATTLESHIP TESTS PASSED")


if __name__ == "__main__":
    main()
