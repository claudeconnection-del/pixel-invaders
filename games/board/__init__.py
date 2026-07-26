"""Shared kit for BOARD-category games (turn-based tabletop clones).

Board games are event-driven, not per-frame sims: a game exposes a pure,
serialisable rules `model` (state / current_turn / legal moves / apply /
winner), and the cabinet-side run drives it hotseat, vs local AI, or online
over the turn-match relay. Elegant animation is a first-class concern, so the
kit provides a small tween/animation queue used by every board game's view.
"""
from games.board.anim import Anim, AnimQueue, ease_out, ease_in_out  # noqa: F401
