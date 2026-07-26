"""A simple, fair Gin Rummy AI: draw the discard only when it lowers the hand's
best post-discard deadwood, otherwise draw blind from the stock; then discard
the card that leaves the least deadwood and knock as soon as that's <= 10.
Uses only the meld engine — no peeking at hidden cards.
"""
from games.rummy.model import KNOCK_MAX, best_deadwood, deadwood


def _best_discard(hand):
    """(card_to_discard, resulting_deadwood) that minimises leftover deadwood."""
    best = None
    for c in hand:
        rest = [x for x in hand if x is not c]
        d = best_deadwood(rest)[0]
        if best is None or d < best[1]:
            best = (c, d)
    return best


def ai_turn(model):
    """Play a full turn (draw + discard, knocking if able) for model.turn.
    Returns a short description, or {'washed': True} if the stock ran out."""
    me = model.turn
    cur = deadwood(model.hands[me])
    take_discard = False
    if model.discard:
        top = model.discard[-1]
        _, after = _best_discard(model.hands[me] + [top])
        take_discard = after < cur          # only if it actually improves us
    if take_discard:
        model.draw("discard")
    elif model.draw("stock") is None:
        return {"washed": True}             # stock exhausted -> hand washed
    card, after = _best_discard(model.hands[me])
    knock = after <= KNOCK_MAX
    model.discard_card(card, knock=knock)
    return {"player": me, "took_discard": take_discard, "discarded": card,
            "knock": knock, "deadwood": after}
