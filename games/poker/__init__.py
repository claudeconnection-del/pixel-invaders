"""Video Poker (5-card draw) — headless core. Rules + paytable + the
deal/hold/draw loop live in model.py; the cabinet view is a later ticket.
"""
from games.poker.model import (  # noqa: F401
    VideoPoker, evaluate, PAYTABLE, RANK_ORDER, LABELS, MAX_BET,
    ROYAL_MAX_BET_JACKPOT)
