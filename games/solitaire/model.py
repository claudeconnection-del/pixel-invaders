"""Klondike Solitaire rules — pure logic, no pygame/GL, deterministic from a
seed. The single source of truth for a game; the cabinet view calls these
methods and reads the piles to draw.

Layout:
- tableau: 7 piles, each {"down": [Card...], "up": [Card...]}. Face-up cards on
  a pile are always a valid descending, alternating-colour run, so ANY suffix
  of `up` is movable (only its bottom card must fit the destination).
- stock: face-down draw pile (draw from the end); waste: face-up (top = end).
- foundations: one pile per suit, built up Ace->King.

Moves each return True iff legal + applied. Every successful move snapshots the
prior state so undo() can step back (undo_count feeds the "no undo" achievement).
Win = all 52 cards on the foundations.
"""
from games.cards.deck import Card, SUITS, make_deck, shuffle


class Solitaire:
    def __init__(self, draw_count=1, pass_limit=None):
        self.draw_count = 3 if draw_count == 3 else 1
        # Vegas: max stock recycles allowed (None = unlimited, the casual rules).
        self.pass_limit = pass_limit
        self.recycles = 0
        self.tableau = [{"down": [], "up": []} for _ in range(7)]
        self.stock = []
        self.waste = []
        self.foundations = {s: [] for s in SUITS}
        self.moves = 0
        self.undo_count = 0
        self.history = []

    # ---------------------------------------------------------------- deal
    def deal(self, rng):
        deck = shuffle(make_deck(), rng)
        self.tableau = [{"down": [], "up": []} for _ in range(7)]
        idx = 0
        for i in range(7):
            for j in range(i + 1):
                card = deck[idx]
                idx += 1
                (self.tableau[i]["up"] if j == i
                 else self.tableau[i]["down"]).append(card)
        self.stock = deck[idx:]            # remaining 24, draw from the end
        self.waste = []
        self.foundations = {s: [] for s in SUITS}
        self.moves = 0
        self.undo_count = 0
        self.recycles = 0
        self.history = []
        return self

    # --------------------------------------------------------- validation
    def _valid_on_tableau(self, card, pile):
        if not pile["up"] and not pile["down"]:
            return card.rank == 13                      # empty pile: King only
        if not pile["up"]:
            return False
        top = pile["up"][-1]
        return card.rank == top.rank - 1 and card.red != top.red

    def _valid_on_foundation(self, card, suit):
        if card.suit != suit:
            return False
        f = self.foundations[suit]
        return card.rank == 1 if not f else card.rank == f[-1].rank + 1

    # ------------------------------------------------------------ history
    def _snapshot(self):
        return {
            "tableau": [{"down": list(p["down"]), "up": list(p["up"])}
                        for p in self.tableau],
            "stock": list(self.stock),
            "waste": list(self.waste),
            "foundations": {s: list(v) for s, v in self.foundations.items()},
            "moves": self.moves,
            "recycles": self.recycles,
        }

    def _restore(self, snap):
        self.tableau = [{"down": list(p["down"]), "up": list(p["up"])}
                        for p in snap["tableau"]]
        self.stock = list(snap["stock"])
        self.waste = list(snap["waste"])
        self.foundations = {s: list(v) for s, v in snap["foundations"].items()}
        self.moves = snap["moves"]
        self.recycles = snap.get("recycles", 0)

    def undo(self):
        if not self.history:
            return False
        self._restore(self.history.pop())
        self.undo_count += 1
        return True

    def _commit(self):
        self.history.append(self._snapshot())

    def _auto_flip(self, pile):
        if not pile["up"] and pile["down"]:
            pile["up"].append(pile["down"].pop())

    # -------------------------------------------------------------- moves
    def draw(self):
        """Turn draw_count cards from stock to waste, or recycle when empty.
        In Vegas (pass_limit set) a recycle beyond the limit is refused."""
        if not self.stock and not self.waste:
            return False
        if not self.stock and self.pass_limit is not None \
                and self.recycles >= self.pass_limit:
            return False                                # out of passes (Vegas)
        self._commit()
        if not self.stock:
            self.stock = list(reversed(self.waste))     # recycle for another pass
            self.waste = []
            self.recycles += 1
        else:
            n = min(self.draw_count, len(self.stock))
            moved = self.stock[-n:]
            del self.stock[-n:]
            self.waste.extend(reversed(moved))          # deepest of the flip on top
        self.moves += 1
        return True

    def waste_to_foundation(self):
        if not self.waste:
            return False
        card = self.waste[-1]
        if not self._valid_on_foundation(card, card.suit):
            return False
        self._commit()
        self.foundations[card.suit].append(self.waste.pop())
        self.moves += 1
        return True

    def waste_to_tableau(self, i):
        if not self.waste:
            return False
        card = self.waste[-1]
        if not self._valid_on_tableau(card, self.tableau[i]):
            return False
        self._commit()
        self.tableau[i]["up"].append(self.waste.pop())
        self.moves += 1
        return True

    def tableau_to_foundation(self, i):
        p = self.tableau[i]
        if not p["up"]:
            return False
        card = p["up"][-1]
        if not self._valid_on_foundation(card, card.suit):
            return False
        self._commit()
        self.foundations[card.suit].append(p["up"].pop())
        self._auto_flip(p)
        self.moves += 1
        return True

    def tableau_to_tableau(self, i, count, j):
        """Move the top `count` face-up cards of pile i onto pile j."""
        if i == j:
            return False
        src = self.tableau[i]
        if count < 1 or count > len(src["up"]):
            return False
        moving = src["up"][-count:]
        if not self._valid_on_tableau(moving[0], self.tableau[j]):
            return False
        self._commit()
        del src["up"][-count:]
        self.tableau[j]["up"].extend(moving)
        self._auto_flip(src)
        self.moves += 1
        return True

    def foundation_to_tableau(self, suit, i):
        f = self.foundations[suit]
        if not f:
            return False
        if not self._valid_on_tableau(f[-1], self.tableau[i]):
            return False
        self._commit()
        self.tableau[i]["up"].append(f.pop())
        self.moves += 1
        return True

    def collect_to_foundations(self):
        """Convenience 'autoplay': move every currently-legal waste/tableau top
        onto a foundation, repeatedly. Returns how many cards moved."""
        moved = 0
        again = True
        while again:
            again = False
            if self.waste_to_foundation():
                moved += 1
                again = True
            for i in range(7):
                if self.tableau_to_foundation(i):
                    moved += 1
                    again = True
        return moved

    # ------------------------------------------------------------ queries
    def tableau_top(self, i):
        up = self.tableau[i]["up"]
        return up[-1] if up else None

    @property
    def cards_home(self):
        return sum(len(v) for v in self.foundations.values())

    @property
    def vegas_delta(self):
        """This deal's Vegas foundation score: +$5 per card currently home.
        Taking a card back off a foundation lowers cards_home, so this tracks
        both directions (+5 to a foundation, -5 off it) with no extra state."""
        return 5 * self.cards_home

    @property
    def won(self):
        return self.cards_home == 52
