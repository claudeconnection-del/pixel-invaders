"""Headless Cabinet Man pilot tests: the Solitaire reference pilot wins a
contrived solvable board, is deterministic from the run's seed, and the
score-integrity + handback plumbing behave. No pygame display, no GL.

Run: python tools/test_pilot.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.cards.deck import Card  # noqa: E402
import games.solitaire.game as solgame  # noqa: E402
from games.solitaire.pilot import create_pilot  # noqa: E402
from arcade.pilot import create_pilot_for, suppress_for_pilot  # noqa: E402
from game.entities import InputState  # noqa: E402


def _solved_setup(run):
    """Mirror test_cards.test_autocomplete_and_double_click: a board with
    nothing face-down and one card left to place — always solvable."""
    run.model.foundations = {"S": [Card(r, "S") for r in range(1, 13)],  # up to Q
                             "H": [Card(r, "H") for r in range(1, 14)],
                             "D": [Card(r, "D") for r in range(1, 14)],
                             "C": [Card(r, "C") for r in range(1, 14)]}
    run.model.tableau = [{"down": [], "up": [Card(13, "S")]}] + \
                        [{"down": [], "up": []} for _ in range(6)]
    run.model.stock, run.model.waste = [], []
    run.won_flag = False


def test_pilot_wins_solvable_board():
    run = solgame.create_run("draw1", random.Random(1))
    _solved_setup(run)
    pilot = create_pilot(run)
    steps = 0
    while not run.model.won and steps < 200:
        assert pilot.step(run, 0.02) is None      # table game: acts directly
        steps += 1
    assert run.model.won and run.won_flag
    print(f"solitaire pilot wins a solvable board OK ({steps} steps)")


def test_pilot_determinism():
    def drive(seed):
        run = solgame.create_run("draw1", random.Random(seed))
        pilot = create_pilot(run)
        for _ in range(400):
            pilot.step(run, 0.03)
            if run.won_flag:
                break
        return (run.model.cards_home, run.model.moves, run.won_flag)

    a = drive(777)
    b = drive(777)
    assert a == b
    print(f"pilot determinism OK (same seed -> {a})")


def test_pilot_opt_in_and_creation():
    run = solgame.create_run("draw1", random.Random(2))
    pilot = create_pilot_for(solgame, run)
    assert pilot is not None and pilot.label == "Cabinet Man"

    class _NoOptIn:
        pass
    assert create_pilot_for(_NoOptIn, run) is None
    print("pilot opt-in (create_pilot_for) OK")


def test_pilot_touched_suppression():
    run = solgame.create_run("draw1", random.Random(3))
    run.pilot_touched = False
    assert not suppress_for_pilot(run)
    pilot = create_pilot(run)
    pilot.step(run, 0.02)
    run.pilot_touched = True          # set by the cabinet loop, as main.py does
    assert suppress_for_pilot(run)
    fresh = solgame.create_run("draw1", random.Random(4))
    assert not suppress_for_pilot(fresh)   # untouched runs are never suppressed
    print("pilot_touched flag + suppression helper OK")


def test_handback_state_machine():
    """The App-level handback: any real input clears the active pilot. Tests
    the pure detection + clearing logic directly (no pygame display needed)."""
    from main import App

    neutral = InputState()
    active = InputState(fire=True)
    assert App._pilot_real_input(active)
    assert not App._pilot_real_input(neutral)

    class _FakeApp:
        def __init__(self):
            self.pilot = object()
            self.wave_banner = None

        def post_banner(self, text, seconds):
            self.wave_banner = (text, seconds)

    fake = _FakeApp()
    App._handback_pilot(fake)
    assert fake.pilot is None and fake.wave_banner is not None
    # idempotent: handing back an already-inactive pilot is a no-op
    fake2 = _FakeApp()
    fake2.pilot = None
    App._handback_pilot(fake2)
    assert fake2.pilot is None and fake2.wave_banner is None
    print("handback state machine OK (real-input detection + flag clear)")


def main():
    test_pilot_wins_solvable_board()
    test_pilot_determinism()
    test_pilot_opt_in_and_creation()
    test_pilot_touched_suppression()
    test_handback_state_machine()
    print("ALL PILOT TESTS PASSED")


if __name__ == "__main__":
    main()
