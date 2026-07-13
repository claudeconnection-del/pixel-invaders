"""Battleship — the cabinet-side game module (BOARD category).

Rules live in games/battleship/model.py; this module is the cabinet's view of
them. It starts with the two projection functions that ARE the secrecy
boundary; the BoardRun subclass, public renderer, INFO and create_run are
added by the cabinet-integration increment.

    public_view(model)       -> what the shared cabinet TV may draw
                                 (shot history + sunk ships; never an un-hit ship)
    secret_view(model, seat) -> the public board PLUS only `seat`'s own fleet
                                 (what that one phone may see)

The invariant that makes "truly secret" true: neither public_view nor any
secret_view for seat S contains hidden state belonging to another seat — for
Battleship, an opponent's un-hit, un-sunk ship cells never appear.
"""
from games.battleship.model import PLAYERS


def _shot_markers(model, target):
    """Public record of shots that have landed on `target`: each fired cell
    tagged hit/miss. Only *fired* cells appear — an un-fired ship cell is never
    revealed, which is exactly fog-of-war."""
    out = []
    for cell in model.shots[target]:
        x, y = cell[0], cell[1]
        out.append({"x": x, "y": y,
                    "hit": model.ship_at(target, x, y) is not None})
    return out


def _sunk_ships(model, player):
    """`player`'s fully-sunk ships, revealed with their cells (sinking is
    announced publicly in Battleship)."""
    return [{"name": s["name"], "cells": [list(c) for c in s["cells"]]}
            for s in model.ships[player] if model.is_sunk(player, s)]


def public_view(model):
    """Everything the shared cabinet screen may draw. Contains no un-hit ship
    for either side."""
    return {
        "size": model.size,
        "phase": model.phase,
        "turn": model.turn,
        "winner": model.winner,
        "boards": {
            p: {
                "shots": _shot_markers(model, p),   # shots that landed on p
                "sunk": _sunk_ships(model, p),      # p's sunk ships (revealed)
                "afloat": model.remaining_ships(p),
            }
            for p in PLAYERS
        },
    }


def secret_view(model, seat):
    """What ONE seat's phone may see: the public board, plus ONLY this seat's
    own fleet (its secret). Adds nothing about the opponent beyond what's
    already public."""
    view = public_view(model)
    view["you"] = seat
    view["your_turn"] = (model.phase == "fire" and model.turn == seat
                         and model.winner is None)
    view["your_fleet"] = [
        {
            "name": s["name"],
            "cells": [list(c) for c in s["cells"]],
            "hits": [[x, y] for x, y in s["cells"]
                     if model.already_shot(seat, x, y)],
            "sunk": model.is_sunk(seat, s),
        }
        for s in model.ships[seat]
    ]
    return view
