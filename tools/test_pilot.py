"""Headless Cabinet Man pilot tests: the Solitaire reference pilot wins a
contrived solvable board, is deterministic from the run's seed, and the
score-integrity + handback plumbing behave; the Serpent reference pilot
plays flawlessly-yet-flamboyantly (safety-checked pathing, glyph-drawing
personality, deterministic replay). No pygame display, no GL.

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

import games.serpent as serpentpkg  # noqa: E402
import games.serpent.game as serpentgame  # noqa: E402
from games.serpent.pilot import create_pilot as create_serpent_pilot  # noqa: E402


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


# ------------------------------------------------------------------ serpent
_DT = 1 / 60
_SERPENT_TARGET_LENGTH = 30       # matches the "Anaconda" achievement threshold
_SERPENT_FRAME_BUDGET = 60 * 60 * 5   # 5 sim-minutes: reaching 30 needs ~1-2


def _drive_serpent(seed, max_frames=_SERPENT_FRAME_BUDGET, target_length=None):
    """Headless sim: cabinet feeds the pilot's own InputState into
    run.update(), same shape as tools/test_games.py's bot-driven loop."""
    run = serpentgame.create_run("arcade", random.Random(seed))
    pilot = create_serpent_pilot(run)
    frames = 0
    died = False
    while frames < max_frames:
        inp = pilot.step(run, _DT)
        run.update(_DT, inp)
        if run.run_over:
            died = True
            break
        frames += 1
        if target_length is not None and run.world.length >= target_length:
            break
    return run, pilot, died, frames


def test_serpent_pilot_reaches_length_without_dying():
    """Red-first requirement: the pilot reaches a solid length on several
    seeds with zero deaths before that point — the flood-fill/tail-safety
    check has to actually be doing its job, not just decorating the code."""
    for seed in (1, 2, 3):
        run, pilot, died, frames = _drive_serpent(seed, target_length=_SERPENT_TARGET_LENGTH)
        assert run.world.length >= _SERPENT_TARGET_LENGTH, \
            f"seed {seed}: pilot only reached length {run.world.length}"
        assert not died, f"seed {seed}: pilot died before reaching length {_SERPENT_TARGET_LENGTH}"
        print(f"serpent pilot seed {seed}: length={run.world.length} "
              f"frames={frames} zero deaths OK")


def _serpent_trap_setup(run):
    """A contrived near-trap board: the fruit sits in a pocket sealed on 3 of
    its 4 sides — the only way in is from the current head. A naive greedy
    1-step-lookahead bot (games/serpent/bot.py's demo_bot) sees the fruit
    cell as merely "not currently occupied" and dives straight in; the real
    safety check has to see that the pocket is a dead end (no path onward to
    the snake's own tail) and refuse it, taking one of the open directions
    instead."""
    world = run.world
    world.body = [(5, 5), (4, 5), (3, 5), (2, 5), (1, 5)]
    world.direction = "right"
    world.pending_direction = "right"
    world.grow = 0
    world.obstacles = {(6, 4), (6, 6), (7, 5)}   # seal the pocket on 3 sides
    world.fruit = (6, 5)                          # bait, sitting in the pocket
    world.fruit_kind = "apple"


def test_serpent_pilot_safety_refuses_trap():
    run = serpentgame.create_run("arcade", random.Random(5))
    _serpent_trap_setup(run)
    pilot = create_serpent_pilot(run)
    inp = pilot.step(run, 0.02)
    assert not inp.right, "pilot dove into a dead-end pocket chasing fruit"
    assert inp.up or inp.down, "pilot didn't take one of the real escape routes"
    print("serpent pilot safety check refuses the trap cell OK")

    # sanity check on the fixture itself: moving right really is a dead end
    # (so the assertion above is testing something real, not a vacuous board)
    # -- i.e. the *only* candidate the pilot rejected was actually unsafe.
    candidates = {name: (new_head, body_after)
                  for name, new_head, body_after in pilot._candidate_moves(run.world)}
    right_head, right_body_after = candidates["right"]
    assert right_head == (6, 5)
    assert not pilot._move_is_safe(right_head, right_body_after, run.world.obstacles), \
        "fixture bug: the pocket isn't actually a dead end"


def test_serpent_pilot_glyph_mode_interleaves_without_dying():
    """The personality half of the ticket: prove glyph waypoints actually
    get executed (not just present in a library nobody reaches) and that
    drawing them never costs the snake its life."""
    run, pilot, died, frames = _drive_serpent(3, max_frames=60 * 60 * 8,
                                               target_length=45)
    assert pilot.glyph_waypoints_hit > 0, "pilot never executed a glyph waypoint"
    assert pilot.glyphs_started, "pilot never attempted a glyph"
    assert not died, "pilot died while drawing glyphs"
    print(f"serpent pilot glyph mode OK: glyphs={pilot.glyphs_started} "
          f"waypoints_hit={pilot.glyph_waypoints_hit} aborted={pilot.glyphs_aborted} "
          f"length={run.world.length}")


def test_serpent_pilot_determinism():
    def drive(seed):
        run, pilot, died, frames = _drive_serpent(seed, max_frames=60 * 60 * 3)
        return (run.world.score, run.world.length, tuple(run.world.body),
                pilot.glyph_waypoints_hit, tuple(pilot.glyphs_started), died)

    a = drive(11)
    b = drive(11)
    assert a == b, f"serpent pilot diverged on identical seed: {a} vs {b}"
    print(f"serpent pilot determinism OK (length={a[1]} score={a[0]})")


def test_serpent_pilot_opt_in():
    """Mirrors games/solitaire/pilot.py's opt-in wiring: main.py's
    `create_pilot_for(self.game, run)` is called with the *package*
    (games.serpent, from games/__init__.py's load_games()), not the game
    submodule directly, so create_pilot has to be re-exported all the way
    up through games/serpent/__init__.py or Cabinet Man silently never
    shows up in-game for this title."""
    run = serpentgame.create_run("arcade", random.Random(6))
    pilot = create_pilot_for(serpentpkg, run)
    assert pilot is not None and pilot.label == "Cabinet Man"
    print("serpent pilot opt-in (package-level create_pilot_for) OK")


def main():
    test_pilot_wins_solvable_board()
    test_pilot_determinism()
    test_pilot_opt_in_and_creation()
    test_pilot_touched_suppression()
    test_handback_state_machine()
    test_serpent_pilot_reaches_length_without_dying()
    test_serpent_pilot_safety_refuses_trap()
    test_serpent_pilot_glyph_mode_interleaves_without_dying()
    test_serpent_pilot_determinism()
    test_serpent_pilot_opt_in()
    print("ALL PILOT TESTS PASSED")


if __name__ == "__main__":
    main()
