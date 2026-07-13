"""Headless companion tests: the secrecy invariant (Increment 1), the session
state machine (Increment 2), and a loopback server round-trip (Increment 3).
No pygame, no GL.

Run: python tools/test_companion.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.battleship.model import BattleshipModel, PLAYERS, OTHER  # noqa: E402
from games.battleship.ai import ai_fire  # noqa: E402
from games.battleship import game as bs  # noqa: E402


def _played_game(seed, max_shots=80):
    """A deterministic game driven by the AI to (usually) a terminal state;
    stops early at max_shots so mid-game states are exercised too."""
    m = BattleshipModel(random.Random(seed))
    m.random_place("P1")
    m.random_place("P2")
    m.begin_fire("P1")
    for _ in range(max_shots):
        if m.winner is not None:
            break
        x, y = ai_fire(m)
        m.fire(m.turn, x, y)
    return m


def _unhit_unsunk_cells(model, player):
    """Cells belonging to `player`'s ships that are neither hit nor part of a
    sunk ship — i.e. the ones that MUST stay secret from the opponent."""
    out = set()
    for s in model.ships[player]:
        if model.is_sunk(player, s):
            continue
        for x, y in s["cells"]:
            if not model.already_shot(player, x, y):
                out.add((x, y))
    return out


def _cells_about(board_view):
    """Every cell a projected board view exposes about that board: fired-at
    cells + revealed sunk-ship cells."""
    cells = {(mk["x"], mk["y"]) for mk in board_view["shots"]}
    for ship in board_view["sunk"]:
        cells |= {tuple(c) for c in ship["cells"]}
    return cells


def test_secrecy_invariant():
    """The core guarantee: no projection leaks an opponent's hidden ships."""
    for seed in range(8):
        m = _played_game(seed)
        pub = bs.public_view(m)
        # public view (the cabinet TV): no un-hit un-sunk ship for EITHER side
        for p in PLAYERS:
            leaked = _cells_about(pub["boards"][p]) & _unhit_unsunk_cells(m, p)
            assert not leaked, f"public_view leaks {p}'s ships {leaked} (seed {seed})"
        # each seat's secret view: reveals nothing new about the OPPONENT, but
        # DOES include the seat's own full fleet
        for seat in PLAYERS:
            sv = bs.secret_view(m, seat)
            other = OTHER[seat]
            leaked = _cells_about(sv["boards"][other]) & _unhit_unsunk_cells(m, other)
            assert not leaked, \
                f"{seat} can see {other}'s hidden ships {leaked} (seed {seed})"
            own_cells = {tuple(c) for s in sv["your_fleet"] for c in s["cells"]}
            actual = {tuple(c) for s in m.ships[seat] for c in s["cells"]}
            assert own_cells == actual, f"{seat} should see its own full fleet"
    print("secrecy invariant OK")


def main():
    test_secrecy_invariant()
    print("ALL COMPANION TESTS PASSED")


if __name__ == "__main__":
    main()
