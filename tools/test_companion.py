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
from games.board.companion.session import SecretLocalSession  # noqa: E402


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


# ------------------------------------------------------------- session tests
def _bs_session(seed=1, code="WAVE"):
    """A SecretLocalSession wired to the Battleship model, with test hooks
    that auto-place fleets on 'ready'."""
    m = BattleshipModel(random.Random(seed))

    def apply_fn(model, seat, a):
        if a["kind"] == "fire":
            return model.fire(seat, a["x"], a["y"])
        return None

    def ready_fn(model, seat, a):
        model.random_place(seat)     # tests auto-place; the game validates layouts
        return True

    def begin_fn(model):
        model.begin_fire("P1")

    return SecretLocalSession(m, secret_fn=bs.secret_view, apply_fn=apply_fn,
                              ready_fn=ready_fn, begin_fn=begin_fn, code=code)


def test_join_rules():
    s = _bs_session()
    assert s.join("NOPE", "Ann")["error"] == "wrong_code"
    a = s.join("WAVE", "Ann")
    assert a["seat"] == "P1" and "token" in a
    assert s.join("WAVE", "Ann")["error"] == "name_taken"
    b = s.join("wave", "Bo")             # code match is case-insensitive
    assert b["seat"] == "P2"
    assert s.join("WAVE", "Cy")["error"] == "full"
    print("join rules OK")


def test_turn_gate_and_versions():
    s = _bs_session()
    a = s.join("WAVE", "Ann")
    b = s.join("WAVE", "Bo")
    s.submit("P1", a["token"], {"kind": "ready"})
    s.submit("P2", b["token"], {"kind": "ready"})
    s.pump(); s.pump()                   # drain both 'ready' actions
    assert s.model.phase == "fire" and s.all_ready()
    v0 = s.poll("P1", a["token"], -1)["v"]
    # P2 fires out of turn -> dropped, no state change, P1's view unchanged
    s.submit("P2", b["token"], {"kind": "fire", "x": 0, "y": 0})
    s.pump()
    assert s.model.turn == "P1"
    assert s.poll("P1", a["token"], v0).get("changed") is False
    # P1 fires in turn -> applied, turn hands off, P1 view version advances
    s.submit("P1", a["token"], {"kind": "fire", "x": 0, "y": 0})
    res = s.pump()
    assert len(res) == 1 and s.model.turn == "P2"
    assert s.poll("P1", a["token"], v0)["v"] > v0
    # bad token rejected
    assert s.submit("P1", "nope", {"kind": "fire", "x": 1, "y": 1})["error"] == "bad_token"
    print("turn gate + versions OK")


def test_anim_gate_blocks_pump():
    s = _bs_session()
    a = s.join("WAVE", "Ann")
    b = s.join("WAVE", "Bo")
    s.submit("P1", a["token"], {"kind": "ready"})
    s.submit("P2", b["token"], {"kind": "ready"})
    s.pump(); s.pump()
    s.gate = True                        # cabinet is "animating"
    s.submit("P1", a["token"], {"kind": "fire", "x": 5, "y": 5})
    assert s.pump() == [] and s.model.turn == "P1"   # gated: nothing applied
    s.gate = False
    assert len(s.pump()) == 1                          # gate cleared -> applies
    print("anim gate OK")


def test_full_game_via_session():
    """Drive a whole game through the session with two AI 'phones', asserting
    secrecy holds after every single move (the invariant, through time)."""
    s = _bs_session(seed=7)
    a = s.join("WAVE", "Ann")
    b = s.join("WAVE", "Bo")
    tok = {"P1": a["token"], "P2": b["token"]}
    s.submit("P1", tok["P1"], {"kind": "ready"})
    s.submit("P2", tok["P2"], {"kind": "ready"})
    s.pump(); s.pump()
    guard = 0
    while s.winner is None and guard < 400:
        seat = s.model.turn
        x, y = ai_fire(s.model)
        s.submit(seat, tok[seat], {"kind": "fire", "x": x, "y": y})
        s.pump()
        for who in ("P1", "P2"):
            view = s.poll(who, tok[who], -1)["view"]
            other = OTHER[who]
            leaked = _cells_about(view["boards"][other]) & _unhit_unsunk_cells(s.model, other)
            assert not leaked, f"{who} leaked {other}'s ships mid-game"
        guard += 1
    assert s.winner in ("P1", "P2")
    print(f"full game via session OK (winner={s.winner}, {guard} shots)")


def main():
    test_secrecy_invariant()
    test_join_rules()
    test_turn_gate_and_versions()
    test_anim_gate_blocks_pump()
    test_full_game_via_session()
    print("ALL COMPANION TESTS PASSED")


if __name__ == "__main__":
    main()
