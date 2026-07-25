"""Headless Video Poker tests: the hand evaluator truth-table, the 9/6 Jacks
or Better paytable (incl. the max-bet royal jackpot), the deal/hold/draw loop
and credits ledger, and a large rng sweep as a smoke-statistic on RTP. No
pygame, no GL.

Run: python tools/test_poker.py
"""
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.cards.deck import Card  # noqa: E402
from games.poker.model import (  # noqa: E402
    MAX_BET, PAYTABLE, ROYAL_MAX_BET_JACKPOT, VideoPoker, evaluate)


def _hand(*specs):
    """('AS', 'KH', ...) -> [Card, ...]. Rank tokens: A,2-10,J,Q,K."""
    labels = {"A": 1, "J": 11, "Q": 12, "K": 13}
    out = []
    for spec in specs:
        rank_s, suit = spec[:-1], spec[-1]
        rank = labels[rank_s] if rank_s in labels else int(rank_s)
        out.append(Card(rank, suit))
    return out


def test_evaluator_truth_table():
    royal = _hand("AS", "KS", "QS", "JS", "10S")
    assert evaluate(royal)[0] == "royal_flush"

    straight_flush = _hand("6H", "7H", "8H", "9H", "10H")
    assert evaluate(straight_flush)[0] == "straight_flush"

    wheel_straight_flush = _hand("AC", "2C", "3C", "4C", "5C")
    assert evaluate(wheel_straight_flush)[0] == "straight_flush"

    wheel_straight = _hand("AC", "2D", "3C", "4H", "5S")
    assert evaluate(wheel_straight)[0] == "straight"

    ace_high_straight = _hand("10C", "JD", "QC", "KH", "AS")
    assert evaluate(ace_high_straight)[0] == "straight"           # not flush

    four_kind = _hand("7S", "7H", "7D", "7C", "2S")
    assert evaluate(four_kind)[0] == "four_kind"

    full_house = _hand("9S", "9H", "9D", "4C", "4S")
    assert evaluate(full_house)[0] == "full_house"

    trips = _hand("9S", "9H", "9D", "4C", "6S")
    assert evaluate(trips)[0] == "three_kind"                      # not a full house

    flush = _hand("2S", "5S", "8S", "JS", "KS")
    assert evaluate(flush)[0] == "flush"

    straight = _hand("4S", "5D", "6C", "7H", "8S")
    assert evaluate(straight)[0] == "straight"

    two_pair = _hand("9S", "9H", "4D", "4C", "6S")
    assert evaluate(two_pair)[0] == "two_pair"

    jacks_pair = _hand("JS", "JH", "4D", "6C", "9S")
    assert evaluate(jacks_pair)[0] == "jacks_or_better"
    aces_pair = _hand("AS", "AH", "4D", "6C", "9S")
    assert evaluate(aces_pair)[0] == "jacks_or_better"

    low_pair = _hand("10S", "10H", "4D", "6C", "9S")
    assert evaluate(low_pair)[0] == "nothing"                      # tens pay nothing

    nothing = _hand("2S", "5D", "9C", "JH", "KS")
    assert evaluate(nothing)[0] == "nothing"

    # royal vs plain straight flush: only the ace-high suited run is royal
    assert evaluate(royal)[0] != evaluate(straight_flush)[0]
    print("evaluator truth-table OK (incl. wheel, ace-high, royal vs SF, "
          "full house vs trips, JoB vs low pair)")


def test_payout_math():
    # per-coin paytable matches the 9/6 full-pay schedule
    assert PAYTABLE == {
        "royal_flush": 250, "straight_flush": 50, "four_kind": 25,
        "full_house": 9, "flush": 6, "straight": 4, "three_kind": 3,
        "two_pair": 2, "jacks_or_better": 1, "nothing": 0,
    }

    vp = VideoPoker(credits=1000, bet=3)
    vp.deal(random.Random(1))
    vp.hand = _hand("9S", "9H", "9D", "4C", "4S")   # full house
    vp.phase = "hold"
    vp.held = [True] * 5
    _, label, won = vp.draw()
    assert label == "Full House" and won == 9 * 3

    # max-bet royal pays the flat jackpot, not 250 * 5
    vp2 = VideoPoker(credits=1000, bet=MAX_BET)
    vp2.deal(random.Random(2))
    vp2.hand = _hand("AS", "KS", "QS", "JS", "10S")
    vp2.phase = "hold"
    vp2.held = [True] * 5
    _, _, won2 = vp2.draw()
    assert won2 == ROYAL_MAX_BET_JACKPOT == 4000
    assert won2 != PAYTABLE["royal_flush"] * MAX_BET

    # a royal at less than max bet gets the plain per-coin payout
    vp3 = VideoPoker(credits=1000, bet=4)
    vp3.deal(random.Random(3))
    vp3.hand = _hand("AS", "KS", "QS", "JS", "10S")
    vp3.phase = "hold"
    vp3.held = [True] * 5
    _, _, won3 = vp3.draw()
    assert won3 == 250 * 4
    print("payout math OK (incl. 4000 max-bet royal jackpot)")


def test_deal_draw_determinism():
    vp_a = VideoPoker(credits=100)
    vp_a.deal(random.Random(42))
    vp_b = VideoPoker(credits=100)
    vp_b.deal(random.Random(42))
    assert vp_a.hand == vp_b.hand and vp_a.phase == "hold" == vp_b.phase
    dealt_hand = list(vp_a.hand)

    # same hold pattern -> identical final hand + result
    for vp in (vp_a, vp_b):
        vp.toggle_hold(0)
        vp.toggle_hold(2)
    res_a = vp_a.draw()
    res_b = vp_b.draw()
    assert vp_a.hand == vp_b.hand
    assert res_a == res_b

    # a fresh deal with the same seed reproduces the same initial hand too
    vp_c = VideoPoker(credits=100)
    vp_c.deal(random.Random(42))
    assert vp_c.hand == dealt_hand
    print("deal/draw determinism OK (same seed -> same final hand)")


def test_credits_ledger():
    vp = VideoPoker(credits=10, bet=4)
    assert vp.deal(random.Random(5))
    assert vp.credits == 6                     # bet deducted
    vp.hand = _hand("2S", "5D", "9C", "JH", "KS")   # a losing hand
    vp.held = [True] * 5
    _, _, won = vp.draw()
    assert won == 0 and vp.credits == 6

    # insufficient credits refuses the deal and leaves the ledger untouched
    vp2 = VideoPoker(credits=2, bet=5)
    assert not vp2.deal(random.Random(6))
    assert vp2.credits == 2 and vp2.phase == "idle"

    # winnings are added back
    vp3 = VideoPoker(credits=100, bet=2)
    vp3.deal(random.Random(7))
    vp3.hand = _hand("7S", "7H", "7D", "7C", "2S")  # four of a kind
    vp3.held = [True] * 5
    vp3.phase = "hold"
    vp3.draw()
    assert vp3.credits == 100 - 2 + 25 * 2
    print("credits ledger OK (deal deducts bet, draw adds winnings)")


def _simple_strategy_holds(hand):
    """A plain-but-sane Jacks-or-Better hold strategy, good enough to be a
    sanity check on RTP (not meant to be optimal)."""
    rank_key, _ = evaluate(hand)
    if rank_key in ("royal_flush", "straight_flush", "four_kind",
                    "full_house", "flush", "straight"):
        return [True] * 5                      # already a made hand: stand pat

    ranks = [c.rank for c in hand]
    suits = [c.suit for c in hand]
    counts = Counter(ranks)

    trips = [r for r, c in counts.items() if c == 3]
    if trips:
        return [c.rank == trips[0] for c in hand]

    pairs = [r for r, c in counts.items() if c == 2]
    if len(pairs) == 2:
        return [c.rank in pairs for c in hand]
    if len(pairs) == 1:
        return [c.rank == pairs[0] for c in hand]

    suit_counts = Counter(suits)
    for s, c in suit_counts.items():
        if c == 4:
            return [card.suit == s for card in hand]

    high_holds = [c.rank in (1, 11, 12, 13) for c in hand]
    if any(high_holds):
        return high_holds
    return [False] * 5


def test_rng_sweep_rtp_smoke():
    rng = random.Random(2024)
    total_bet = 0
    total_won = 0
    seen_ranks = set()
    n = 10_000
    for _ in range(n):
        vp = VideoPoker(credits=10**9, bet=1)
        assert vp.deal(rng)
        for i, hold in enumerate(_simple_strategy_holds(vp.hand)):
            if hold:
                vp.toggle_hold(i)
        rank_key, label, won = vp.draw()
        seen_ranks.add(rank_key)
        total_bet += 1
        total_won += won
    rtp = total_won / total_bet
    assert 0.85 <= rtp <= 1.02, f"RTP {rtp:.3f} outside sane band"
    assert len(seen_ranks) >= 8, f"suspiciously few hand classes hit: {seen_ranks}"
    print(f"rng sweep OK ({n} hands, no evaluator crash, RTP={rtp:.3f}, "
          f"{len(seen_ranks)}/10 hand classes hit)")


def main():
    test_evaluator_truth_table()
    test_payout_math()
    test_deal_draw_determinism()
    test_credits_ledger()
    test_rng_sweep_rtp_smoke()
    print("ALL POKER TESTS PASSED")


if __name__ == "__main__":
    main()
