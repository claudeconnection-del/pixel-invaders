"""A standard 52-card deck — pure logic, no pygame/GL.

Cards are immutable (rank 1..13, suit in SHDC); games track face-up state and
pile membership themselves. Ranks: 1=Ace .. 11=J, 12=Q, 13=K. Suits hearts and
diamonds are red, spades and clubs black.
"""
from dataclasses import dataclass

SUITS = ("S", "H", "D", "C")       # spades, hearts, diamonds, clubs
RANKS = list(range(1, 14))         # Ace(1) .. King(13)
_RED = ("H", "D")
_RANK_LABEL = {1: "A", 11: "J", 12: "Q", 13: "K"}


@dataclass(frozen=True)
class Card:
    rank: int
    suit: str

    @property
    def red(self):
        return self.suit in _RED

    @property
    def rank_label(self):
        return _RANK_LABEL.get(self.rank, str(self.rank))

    @property
    def label(self):
        return f"{self.rank_label}{self.suit}"

    def to_tuple(self):
        return (self.rank, self.suit)

    @classmethod
    def from_tuple(cls, t):
        return cls(int(t[0]), t[1])


def make_deck():
    """A fresh ordered 52-card deck."""
    return [Card(r, s) for s in SUITS for r in RANKS]


def shuffle(deck, rng):
    """Return a shuffled copy (deterministic given `rng`)."""
    out = list(deck)
    rng.shuffle(out)
    return out
