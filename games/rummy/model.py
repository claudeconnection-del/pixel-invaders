"""Gin Rummy rules + meld engine — pure logic, no pygame/GL, deterministic from
a seed. Two players (the human vs a simple AI, wired later). Standard Gin:
deal 10 each, draw from stock or discard then discard one; form melds (sets of
3-4 same rank, runs of 3+ in suit, Ace low); knock when your deadwood <= 10, or
gin at 0. (Lay-offs onto the knocker's melds are intentionally omitted in this
first version — noted for a later pass.)

The meld engine (`best_deadwood`) finds the arrangement of non-overlapping melds
that minimises leftover "deadwood" value — the heart of Rummy, shared by the AI
and (later) the view.
"""
from collections import defaultdict
from itertools import combinations

from games.cards.deck import make_deck, shuffle

PLAYERS = ("P1", "P2")
OTHER = {"P1": "P2", "P2": "P1"}
HAND_SIZE = 10
KNOCK_MAX = 10          # may knock when deadwood <= 10
GIN_BONUS = 25
UNDERCUT_BONUS = 25


def deadwood_value(rank):
    """Card value for deadwood/scoring: Ace 1, face cards 10, else pip."""
    return min(rank, 10)


def all_melds(cards):
    """Every valid meld (list of Card) formable from `cards`: sets (3-4 of a
    rank) and runs (3+ consecutive in a suit, Ace low)."""
    melds = []
    by_rank = defaultdict(list)
    for c in cards:
        by_rank[c.rank].append(c)
    for group in by_rank.values():
        if len(group) >= 3:
            for combo in combinations(group, 3):
                melds.append(list(combo))
            if len(group) >= 4:
                melds.append(list(group))
    by_suit = defaultdict(dict)
    for c in cards:
        by_suit[c.suit][c.rank] = c        # one card per (suit, rank) in a deck
    for cardby in by_suit.values():
        ranks = sorted(cardby)
        for i in range(len(ranks)):
            run = [ranks[i]]
            for r in ranks[i + 1:]:
                if r == run[-1] + 1:
                    run.append(r)
                else:
                    break
            for length in range(3, len(run) + 1):
                melds.append([cardby[r] for r in run[:length]])
    return melds


def best_deadwood(cards):
    """(deadwood_value, chosen_melds) for the partition of `cards` into
    non-overlapping melds that minimises deadwood."""
    cards = list(cards)
    total = sum(deadwood_value(c.rank) for c in cards)
    melds = all_melds(cards)
    pos = {c: i for i, c in enumerate(cards)}
    masks = []
    for m in melds:
        mask = 0
        val = 0
        for c in m:
            mask |= 1 << pos[c]
            val += deadwood_value(c.rank)
        masks.append((mask, val))

    best = {"covered": 0, "sel": ()}

    def rec(i, used, covered, sel):
        if covered > best["covered"]:
            best["covered"] = covered
            best["sel"] = tuple(sel)
        for j in range(i, len(masks)):
            mask, val = masks[j]
            if not (mask & used):
                sel.append(j)
                rec(j + 1, used | mask, covered + val, sel)
                sel.pop()

    rec(0, 0, 0, [])
    chosen = [melds[j] for j in best["sel"]]
    return total - best["covered"], chosen


def deadwood(cards):
    return best_deadwood(cards)[0]


class GinRummy:
    def __init__(self, rng=None, target=100):
        self.rng = rng
        self.target = target
        self.scores = {"P1": 0, "P2": 0}
        self.hands = {"P1": [], "P2": []}
        self.stock = []
        self.discard = []
        self.turn = "P1"
        self.phase = "draw"        # draw -> discard -> (next turn)
        self.hand_over = False
        self.game_over = False
        self.result = None         # last hand result dict
        if rng is not None:
            self.deal()

    # ------------------------------------------------------------- lifecycle
    def deal(self, first="P1"):
        deck = shuffle(make_deck(), self.rng)
        self.hands = {"P1": deck[0:10], "P2": deck[10:20]}
        self.discard = [deck[20]]
        self.stock = deck[21:]
        self.turn = first
        self.phase = "draw"
        self.hand_over = False
        self.result = None

    def hand(self, player=None):
        return self.hands[player or self.turn]

    # --------------------------------------------------------------- moves
    def draw(self, source):
        """Draw for the player to move, from 'stock' or 'discard'."""
        if self.phase != "draw" or self.hand_over:
            return None
        if source == "discard":
            if not self.discard:
                return None
            card = self.discard.pop()
        else:
            if not self.stock:
                self._wash()               # stock empty: no-score redeal
                return None
            card = self.stock.pop()
        self.hands[self.turn].append(card)
        self.phase = "discard"
        return card

    def can_knock(self, player=None):
        return deadwood(self.hands[player or self.turn]) <= KNOCK_MAX

    def discard_card(self, card, knock=False):
        """Discard `card` from the mover's hand. If knock and the remaining
        hand's deadwood <= 10, end the hand. Returns True if applied."""
        if self.phase != "discard" or self.hand_over:
            return False
        hand = self.hands[self.turn]
        if card not in hand:
            return False
        if knock and deadwood([c for c in hand if c is not card]) > KNOCK_MAX:
            return False
        hand.remove(card)
        self.discard.append(card)
        if knock:
            self._end_hand(self.turn)
        else:
            self.turn = OTHER[self.turn]
            self.phase = "draw"
            if not self.stock:
                self._wash()
        return True

    # ------------------------------------------------------------- scoring
    def _end_hand(self, knocker):
        opp = OTHER[knocker]
        k_dead, k_melds = best_deadwood(self.hands[knocker])
        o_dead, o_melds = best_deadwood(self.hands[opp])
        gin = k_dead == 0
        if gin:
            winner, points = knocker, o_dead + GIN_BONUS
        elif o_dead > k_dead:
            winner, points = knocker, o_dead - k_dead
        else:                              # undercut
            winner, points = opp, (k_dead - o_dead) + UNDERCUT_BONUS
        self.scores[winner] += points
        self.result = {
            "knocker": knocker, "winner": winner, "points": points, "gin": gin,
            "deadwood": {knocker: k_dead, opp: o_dead},
            "melds": {knocker: k_melds, opp: o_melds},
        }
        self.hand_over = True
        if self.scores[winner] >= self.target:
            self.game_over = True

    def _wash(self):
        self.result = {"washed": True}
        self.hand_over = True
