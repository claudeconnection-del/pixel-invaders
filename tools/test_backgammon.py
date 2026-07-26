"""Headless Backgammon tests: board invariants, legal-move edge cases (bar
entry/blocking, hitting, doubles, forced higher-die, bear-off exact/overshoot),
grading, and an AI-vs-AI game driven to completion plus a win-rate check
against a random-legal-move baseline. No pygame, no GL.

Run: python tools/test_backgammon.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.backgammon.model import (  # noqa: E402
    Backgammon, OTHER, START_POINTS, checker_count, pip_count)
from games.backgammon.ai import ai_move, random_move  # noqa: E402


def _assert_conserved(m):
    for p in ("A", "B"):
        assert checker_count(m.points, m.bar, m.off, p) == 15, \
            f"{p} checker count drifted: {m.points} bar={m.bar} off={m.off}"


def test_start_position():
    m = Backgammon(random.Random(1))
    assert list(m.points) == list(START_POINTS)
    _assert_conserved(m)
    # standard pip counts for the opening position: 167 each side
    assert m.pip_count("A") == 167
    assert m.pip_count("B") == 167
    print("start position + checker conservation OK")


def test_bar_entry_and_blocking():
    m = Backgammon(random.Random(2))
    m.points = [0] * 24
    # B makes a full prime on A's entry points (indices 18-23) except one
    for i in range(18, 24):
        m.points[i] = -2
    m.bar = {"A": 1, "B": 0}
    m.off = {"A": 14, "B": 3}   # 12 on the prime + 3 off = 15
    # every entry point blocked -> no legal moves at all with any die
    seqs = m.legal_moves("A", [3, 5])
    assert seqs == [()], f"expected no legal entry, got {seqs}"

    # open one entry point (die 4 -> index 20) as a blot -> enters + hits
    m.points[20] = -1
    m.off["B"] = 4   # one fewer on the board -> one more off, still 15 total
    seqs = m.legal_moves("A", [4, 6])
    assert any(s and s[0]["from"] == "bar" and s[0]["to"] == 20 and s[0]["hit"]
               for s in seqs)
    m.apply(next(s for s in seqs if s[0]["to"] == 20))
    assert m.bar["A"] == 0 and m.bar["B"] == 1
    _assert_conserved(m)
    print("bar entry blocking + entry-hit OK")


def test_blot_hitting_mid_board():
    m = Backgammon(random.Random(3))
    m.points = [0] * 24
    m.points[10] = 1     # lone A checker
    m.points[13] = 2
    m.points[7] = -1     # lone B checker in its path (A moves down)
    m.points[20] = -12   # rest of B's checkers parked, off home for now
    m.bar = {"A": 0, "B": 0}
    m.off = {"A": 12, "B": 2}   # A: 1+2+12=15; B: 1+12+2=15
    seqs = m.legal_moves("A", [3, 1])
    hit_seqs = [s for s in seqs if any(mv.get("hit") for mv in s)]
    assert hit_seqs, "expected a sequence that hits the B blot on index 7"
    m.apply(hit_seqs[0])
    assert m.bar["B"] == 1   # the B blot was sent to the bar
    _assert_conserved(m)
    print("blot hitting OK")


def test_doubles_four_moves():
    m = Backgammon(random.Random(4))
    # from the start position, rolling double 2s: A can move four checkers
    seqs = m.legal_moves("A", [2, 2, 2, 2])
    assert max(len(s) for s in seqs) == 4
    assert all(len(s) <= 4 for s in seqs)
    m.apply(next(s for s in seqs if len(s) == 4))
    _assert_conserved(m)
    print("doubles = up to four moves OK")


def test_forced_higher_die():
    m = Backgammon(random.Random(5))
    m.points = [0] * 24
    # one lone A checker at index 10 (mid-board, no bear-off complexity).
    # die 2 alone -> index 8 (open); die 5 alone -> index 5 (open); but
    # playing BOTH (in either order, since it's the same single checker)
    # lands on index 3 either way -- block index 3 so neither order can
    # chain to a second move: each die is legal alone, never both together.
    m.points[10] = 1
    m.points[3] = -2                    # blocks the combined destination
    m.off = {"A": 14, "B": 13}          # A: 1+14=15; B: 2+13=15
    m.bar = {"A": 0, "B": 0}
    seqs = m.legal_moves("A", [2, 5])
    assert max(len(s) for s in seqs) == 1
    # both dice are individually legal (8 and 5 are open) but never together
    # -> forced-play rule requires the larger die (5).
    assert all(s[0]["die"] == 5 for s in seqs)
    print("forced higher-die rule OK")


def test_bear_off_exact_and_overshoot():
    m = Backgammon(random.Random(6))
    m.points = [0] * 24
    m.points[2] = 1   # distance 3 (exact point)
    m.points[4] = 1   # distance 5 (highest occupied home point)
    m.off = {"A": 13, "B": 15}   # A: 1+1+13=15; B: all borne off already
    m.bar = {"A": 0, "B": 0}
    # exact roll of 3 bears off the index-2 checker
    seqs = m.legal_moves("A", [3, 1])
    exact = [s for s in seqs if any(
        mv["from"] == 2 and mv["to"] == "off" for mv in s)]
    assert exact, "exact bear-off with die 3 should be legal"

    # die 6 overshoots both checkers; only the highest occupied point at the
    # start of the turn (index4, dist5) may bear off with the FIRST 6 -- the
    # index2 checker (dist3) may not, since it isn't the highest point yet
    seqs6 = m.legal_moves("A", [6, 6, 6, 6])
    for s in seqs6:
        if s[0]["to"] == "off":
            assert s[0]["from"] == 4, f"illegal overshoot bear-off: {s[0]}"
    assert any(s[0]["to"] == "off" and s[0]["from"] == 4 for s in seqs6)
    print("bear-off exact + overshoot OK")


def test_gammon_and_backgammon_grading():
    # gammon: loser bears off nothing, no loser checker on bar or in winner's home
    m = Backgammon(random.Random(7))
    m.points = [0] * 24
    m.points[0] = 1
    m.points[10] = -5  # loser's checkers well clear of winner's (A's) home (0-5)
    m.points[15] = -10
    m.bar = {"A": 0, "B": 0}
    m.off = {"A": 14, "B": 0}
    seqs = m.legal_moves("A", [1, 2])
    bear = next(s for s in seqs if any(mv["to"] == "off" for mv in s))
    m.apply(bear)
    assert m.winner == "A"
    assert m.result["grade"] == "gammon", m.result
    _assert_conserved(m)

    # backgammon: loser has a checker on the bar (or in winner's home) when
    # the winner finishes and the loser has borne off none
    m2 = Backgammon(random.Random(8))
    m2.points = [0] * 24
    m2.points[0] = 1
    m2.points[10] = -14
    m2.bar = {"A": 0, "B": 1}
    m2.off = {"A": 14, "B": 0}
    seqs2 = m2.legal_moves("A", [1, 2])
    bear2 = next(s for s in seqs2 if any(mv["to"] == "off" for mv in s))
    m2.apply(bear2)
    assert m2.winner == "A"
    assert m2.result["grade"] == "backgammon", m2.result
    print("gammon/backgammon grading OK")


def _play_ai_game(seed):
    m = Backgammon(random.Random(seed))
    guard = 0
    while m.winner is None:
        m.roll()
        ai_move(m)
        guard += 1
        assert guard < 5000, "game did not progress"
        _assert_conserved(m)
    return m


def test_ai_vs_ai_deterministic():
    m1 = _play_ai_game(42)
    m2 = _play_ai_game(42)
    assert m1.winner == m2.winner
    assert m1.result == m2.result
    print(f"AI-vs-AI deterministic completion OK (winner={m1.winner}, "
          f"grade={m1.result['grade']})")


def _play_ai_vs_random(seed):
    """A (greedy AI) vs B (random-legal baseline); returns the winner."""
    m = Backgammon(random.Random(seed))
    baseline_rng = random.Random(seed + 1_000_000)
    guard = 0
    while m.winner is None:
        m.roll()
        if m.turn == "A":
            ai_move(m)
        else:
            random_move(m, baseline_rng)
        guard += 1
        assert guard < 5000, "game did not progress"
    return m.winner


def test_ai_beats_random_baseline():
    n = 200
    wins = sum(1 for seed in range(n) if _play_ai_vs_random(seed) == "A")
    rate = wins / n
    assert rate >= 0.80, f"greedy AI only won {rate:.0%} of {n} games vs random"
    print(f"AI vs random baseline OK ({wins}/{n} = {rate:.0%} win rate)")


def test_backgammon_achievements():
    from games.backgammon.achievements import ACHIEVEMENTS
    by = {a.id: a for a in ACHIEVEMENTS}
    assert by["bg_first_win"].check("bg_win", {}, {}, {})
    assert not by["bg_first_win"].check("bg_lose", {}, {}, {})
    assert by["gammon"].check("bg_win", {"grade": "gammon"}, {}, {})
    assert not by["gammon"].check("bg_win", {"grade": "single"}, {}, {})
    assert by["backgammon_win"].check("bg_win", {"grade": "backgammon"}, {}, {})
    assert by["pip_race"].check("bg_win", {}, {}, {"max_pip_deficit": 30})
    assert not by["pip_race"].check("bg_win", {}, {}, {"max_pip_deficit": 29})
    assert by["bg_games_100"].check(None, None, {"bg_games": 100}, {})
    assert by["bg_wins_50"].check(None, None, {"bg_wins": 50}, {})
    assert by["bg_games_100"].progress({"bg_games": 40}, {}) == (40, 100)
    # ids must not collide with the other tabletop games' skin-gate ids
    from games.solitaire.achievements import ACHIEVEMENTS as SOL
    from games.rummy.achievements import ACHIEVEMENTS as RUM
    from games.poker.achievements import ACHIEVEMENTS as POK
    other_ids = {a.id for a in SOL} | {a.id for a in RUM} | {a.id for a in POK}
    assert not (set(by) & other_ids)
    print(f"backgammon achievements OK ({len(ACHIEVEMENTS)} incl. grind, no id collision)")


def test_backgammon_wiring():
    import games.backgammon.game as bggame
    from meta.achievements import AchievementEngine

    run = bggame.create_run("standard", random.Random(11))
    section = {"achievements": {}, "lifetime": {}, "unlocked_skins": []}
    settings = {}
    run.attach_profile(section, settings, lambda: None)
    assert section["lifetime"]["bg_games"] == 1

    run._max_pip_deficit = 40
    run.model.winner = "A"
    run.model.result = {"winner": "A", "loser": "B", "grade": "gammon"}
    run._announce_result()

    assert section["lifetime"]["bg_wins"] == 1
    assert section["lifetime"]["bg_gammons"] == 1

    engine = AchievementEngine(section, bggame.ACHIEVEMENTS)
    unlocked = {a.id for a in engine.on_frame(run.drain_events(), run.run_stats())}
    assert {"bg_first_win", "gammon", "pip_race"} <= unlocked

    run.update(0.016, None)
    assert "noir_lacquer" in settings["tabletop"]["unlocked_boards"]
    print("backgammon wiring OK (achievements + grind counters + board unlock sync)")


def main():
    test_start_position()
    test_bar_entry_and_blocking()
    test_blot_hitting_mid_board()
    test_doubles_four_moves()
    test_forced_higher_die()
    test_bear_off_exact_and_overshoot()
    test_gammon_and_backgammon_grading()
    test_ai_vs_ai_deterministic()
    test_ai_beats_random_baseline()
    test_backgammon_achievements()
    test_backgammon_wiring()
    print("ALL BACKGAMMON TESTS PASSED")


if __name__ == "__main__":
    main()
