"""Headless tabletop tests: the card deck, the deck/felt skin registries, and
the Klondike Solitaire rules. No pygame, no GL.

Run: python tools/test_cards.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.cards import skins  # noqa: E402
from games.cards.deck import Card, SUITS, make_deck, shuffle  # noqa: E402
from games.solitaire.model import Solitaire  # noqa: E402


def test_deck():
    d = make_deck()
    assert len(d) == 52 and len(set(d)) == 52
    assert sum(1 for c in d if c.suit == "H") == 13
    assert Card(1, "H").red and Card(1, "D").red
    assert not Card(1, "S").red and not Card(1, "C").red
    assert Card(1, "S").label == "AS"
    assert Card(13, "H").label == "KH" and Card(10, "C").label == "10C"
    # deterministic shuffle, and it actually reorders
    a = shuffle(d, random.Random(5))
    b = shuffle(d, random.Random(5))
    assert a == b and a != d
    print("deck OK")


def test_skins():
    free = skins.available_decks(set())
    assert all(s.premium is None for s in free)
    prem = [s for s in skins.DECKS if s.premium]
    assert prem, "expected premium decks"
    p = prem[0]
    assert p.id not in {s.id for s in free}
    assert p.id in {s.id for s in skins.available_decks({p.premium})}
    # felts: dynamic ones expose their ambient scene id
    assert skins.felt_by_id("galaxy").scene == "nebula"
    assert skins.felt_by_id("classic_green").scene is None
    # round-trip
    assert skins.DeckSkin.from_dict(skins.DECKS[0].to_dict()) == skins.DECKS[0]
    assert skins.FeltSkin.from_dict(skins.FELTS[0].to_dict()) == skins.FELTS[0]
    print(f"skins OK ({len(skins.DECKS)} decks, {len(skins.FELTS)} felts, "
          f"{len(prem)} premium decks)")


def test_deal():
    m = Solitaire().deal(random.Random(7))
    total = sum(len(p["down"]) + len(p["up"]) for p in m.tableau)
    assert total == 28
    for i, p in enumerate(m.tableau):
        assert len(p["up"]) == 1 and len(p["down"]) == i
    assert len(m.stock) == 24 and m.cards_home == 0 and not m.won
    allcards = [c for p in m.tableau for c in p["down"] + p["up"]] + m.stock
    assert len(allcards) == 52 and len(set(allcards)) == 52
    # deterministic from the seed
    b = Solitaire().deal(random.Random(7))
    assert [c.to_tuple() for c in m.stock] == [c.to_tuple() for c in b.stock]
    print("deal OK")


def test_stock_draw_recycle():
    m = Solitaire(draw_count=1).deal(random.Random(1))
    assert m.draw() and len(m.waste) == 1 and len(m.stock) == 23
    while m.stock:
        m.draw()
    assert len(m.waste) == 24 and not m.stock
    assert m.draw() and len(m.stock) == 24 and not m.waste  # recycled
    # draw-3 moves three at a time
    m3 = Solitaire(draw_count=3).deal(random.Random(1))
    m3.draw()
    assert len(m3.waste) == 3
    print("stock draw + recycle OK")


def test_move_rules_and_undo():
    m = Solitaire()
    m.tableau = [{"down": [Card(5, "S")], "up": [Card(1, "H")]}] + \
                [{"down": [], "up": []} for _ in range(6)]
    m.foundations = {s: [] for s in SUITS}
    # ace to foundation, and the buried 5S auto-flips up
    assert m.tableau_to_foundation(0)
    assert m.tableau[0]["up"] == [Card(5, "S")] and not m.tableau[0]["down"]
    assert m.cards_home == 1
    # undo restores the exact prior state and counts the undo
    assert m.undo() and m.undo_count == 1
    assert m.tableau[0]["up"] == [Card(1, "H")] and m.tableau[0]["down"] == [Card(5, "S")]
    assert m.cards_home == 0

    # tableau run move: [6H,5S] onto a black 7 is legal; onto a red 7 is not
    m.tableau = [{"down": [], "up": [Card(6, "H"), Card(5, "S")]},
                 {"down": [], "up": [Card(7, "S")]},
                 {"down": [], "up": [Card(7, "H")]}] + \
                [{"down": [], "up": []} for _ in range(4)]
    assert not m.tableau_to_tableau(0, 2, 2)          # 6H onto 7H: same colour
    assert m.tableau_to_tableau(0, 2, 1)              # 6H onto 7S: ok
    assert [c.to_tuple() for c in m.tableau[1]["up"]] == [(7, "S"), (6, "H"), (5, "S")]
    assert not m.tableau[0]["up"]

    # empty pile only accepts a King
    m.tableau = [{"down": [], "up": [Card(13, "D")]},
                 {"down": [], "up": [Card(9, "C")]}] + \
                [{"down": [], "up": []} for _ in range(5)]
    assert not m.tableau_to_tableau(1, 1, 2)          # 9C to empty: rejected
    assert m.tableau_to_tableau(0, 1, 2)              # KD to empty: ok
    print("move rules + undo OK")


def test_collect_and_win():
    m = Solitaire()
    full = lambda s: [Card(r, s) for r in range(1, 14)]
    m.foundations = {"S": full("S"), "H": full("H"), "D": full("D"),
                     "C": [Card(r, "C") for r in range(1, 13)]}  # C up to Queen
    m.tableau = [{"down": [], "up": [Card(13, "C")]}] + \
                [{"down": [], "up": []} for _ in range(6)]
    assert not m.won and m.cards_home == 51
    moved = m.collect_to_foundations()
    assert moved == 1 and m.won and m.cards_home == 52
    print("collect + win OK")


def test_solitaire_achievements():
    from games.solitaire.achievements import ACHIEVEMENTS
    by = {a.id: a for a in ACHIEVEMENTS}
    assert by["first_win"].check("sol_win", None, {}, {})
    assert not by["first_win"].check("sol_deal", None, {}, {})
    assert by["speed_run"].check("sol_win", None, {}, {"time": 120})
    assert not by["speed_run"].check("sol_win", None, {}, {"time": 999})
    assert by["no_undo"].check("sol_win", None, {}, {"undos": 0})
    assert not by["no_undo"].check("sol_win", None, {}, {"undos": 2})
    assert by["streak_3"].check("sol_win", None, {"sol_streak": 3}, {})
    assert not by["streak_3"].check("sol_win", None, {"sol_streak": 2}, {})
    # grind milestones fire from counters alone (progress-checked every frame)
    assert by["century"].check(None, None, {"sol_games": 100}, {})
    assert not by["century"].check(None, None, {"sol_games": 99}, {})
    assert by["millennium"].check(None, None, {"sol_games": 1000}, {})
    assert by["founder"].check(None, None, {"sol_wins": 250}, {})
    assert by["century"].progress({"sol_games": 40}, {}) == (40, 100)
    assert by["millennium"].progress({"sol_games": 5000}, {}) == (1000, 1000)
    print(f"solitaire achievements OK ({len(ACHIEVEMENTS)} incl. grind)")


def main():
    test_deck()
    test_skins()
    test_deal()
    test_stock_draw_recycle()
    test_move_rules_and_undo()
    test_collect_and_win()
    test_solitaire_achievements()
    print("ALL CARD TESTS PASSED")


if __name__ == "__main__":
    main()
