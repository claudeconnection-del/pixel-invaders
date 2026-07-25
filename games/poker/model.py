"""5-card-draw Video Poker rules — pure logic, no pygame/GL, deterministic from
a seed. Full-pay 9/6 Jacks or Better: `evaluate()` classifies a 5-card hand,
`PAYTABLE` is the per-coin payout schedule, `VideoPoker` runs the deal/hold/
draw loop and keeps a simple credits ledger. The cabinet view (a later ticket)
calls these methods and reads the hand/held state to draw.

Ace plays both high (the A-K-Q-J-10 royal) and low (the A-2-3-4-5 "wheel"
straight) — never both in the same hand, since a straight needs 5 distinct
ranks.
"""
from collections import Counter

from games.cards.deck import make_deck, shuffle

MAX_BET = 5

# Full-pay 9/6 Jacks or Better, per-coin (i.e. per unit of `bet`).
PAYTABLE = {
    "royal_flush": 250,
    "straight_flush": 50,
    "four_kind": 25,
    "full_house": 9,
    "flush": 6,
    "straight": 4,
    "three_kind": 3,
    "two_pair": 2,
    "jacks_or_better": 1,
    "nothing": 0,
}

# Weakest -> strongest, matching PAYTABLE's keys.
RANK_ORDER = [
    "nothing", "jacks_or_better", "two_pair", "three_kind", "straight",
    "flush", "full_house", "four_kind", "straight_flush", "royal_flush",
]

LABELS = {
    "royal_flush": "Royal Flush",
    "straight_flush": "Straight Flush",
    "four_kind": "Four of a Kind",
    "full_house": "Full House",
    "flush": "Flush",
    "straight": "Straight",
    "three_kind": "Three of a Kind",
    "two_pair": "Two Pair",
    "jacks_or_better": "Jacks or Better",
    "nothing": "Nothing",
}

_JACKS_OR_BETTER_RANKS = (1, 11, 12, 13)   # Ace, Jack, Queen, King

# Max-bet (5 coins) royal flush pays a flat jackpot instead of 250 * 5.
ROYAL_MAX_BET_JACKPOT = 4000


def _straight_high(ranks):
    """The straight's high card value if `ranks` (5 ints) form a straight,
    else None. Ace(1) plays low in the wheel (A-2-3-4-5, high=5) and high in
    the broadway straight (10-J-Q-K-A, high=14)."""
    values = sorted(set(ranks))
    if len(values) != 5:
        return None
    if values == [1, 2, 3, 4, 5]:
        return 5
    if values == [1, 10, 11, 12, 13]:
        return 14
    if values[4] - values[0] == 4:
        return values[4]
    return None


def evaluate(cards):
    """Classify a 5-card hand (list of Card). Returns (rank_key, label)
    where `rank_key` is one of PAYTABLE's keys (also indexes RANK_ORDER) and
    `label` is a human-readable name."""
    ranks = [c.rank for c in cards]
    suits = [c.suit for c in cards]
    counts = Counter(ranks)
    count_vals = sorted(counts.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(ranks)
    is_straight = straight_high is not None

    if is_straight and is_flush:
        key = "royal_flush" if straight_high == 14 else "straight_flush"
    elif count_vals == [4, 1]:
        key = "four_kind"
    elif count_vals == [3, 2]:
        key = "full_house"
    elif is_flush:
        key = "flush"
    elif is_straight:
        key = "straight"
    elif count_vals == [3, 1, 1]:
        key = "three_kind"
    elif count_vals == [2, 2, 1]:
        key = "two_pair"
    elif count_vals == [2, 1, 1, 1]:
        pair_rank = next(r for r, c in counts.items() if c == 2)
        key = "jacks_or_better" if pair_rank in _JACKS_OR_BETTER_RANKS else "nothing"
    else:
        key = "nothing"
    return key, LABELS[key]


class VideoPoker:
    """One 5-card-draw round at a time. `deal` -> toggle_hold* -> `draw`.

    Phases: "idle" (no hand yet / after a full round, before the next deal),
    "hold" (hand dealt, holds may be toggled), "paid" (drawn + settled).
    """

    def __init__(self, credits=100, bet=1):
        self.credits = credits
        self._bet = 1
        self.bet = bet
        self.deck = []
        self.hand = []
        self.held = [False] * 5
        self.phase = "idle"
        self.last_result = None    # (rank_key, label, won) after draw()

    @property
    def bet(self):
        return self._bet

    @bet.setter
    def bet(self, value):
        value = int(value)
        if not 1 <= value <= MAX_BET:
            raise ValueError(f"bet must be 1-{MAX_BET}, got {value}")
        self._bet = value

    def deal(self, rng):
        """Shuffle a fresh deck, deal 5 cards, deduct the bet. Returns True
        iff there were enough credits to cover the bet."""
        if self.credits < self.bet:
            return False
        self.credits -= self.bet
        self.deck = shuffle(make_deck(), rng)
        self.hand = self.deck[:5]
        self.deck = self.deck[5:]      # remainder is the draw pile
        self.held = [False] * 5
        self.phase = "hold"
        self.last_result = None
        return True

    def toggle_hold(self, i):
        """Flip whether card `i` (0-4) is held. Only legal during "hold"."""
        if self.phase != "hold" or not 0 <= i < 5:
            return False
        self.held[i] = not self.held[i]
        return True

    def draw(self):
        """Replace un-held cards from the same deck, evaluate, pay out.
        Returns (rank_key, label, won), or None if not in "hold" phase."""
        if self.phase != "hold":
            return None
        for i in range(5):
            if not self.held[i]:
                self.hand[i] = self.deck.pop(0)
        rank_key, label = evaluate(self.hand)
        if rank_key == "royal_flush" and self.bet == MAX_BET:
            won = ROYAL_MAX_BET_JACKPOT
        else:
            won = PAYTABLE[rank_key] * self.bet
        self.credits += won
        self.phase = "paid"
        self.last_result = (rank_key, label, won)
        return self.last_result
