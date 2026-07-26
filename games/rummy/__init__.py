"""Gin Rummy — solo vs a simple AI. Rules + meld engine in model.py; the
cabinet view + INFO in game.py.
"""
from games.rummy.model import GinRummy, best_deadwood, all_melds  # noqa: F401
from games.rummy.game import (  # noqa: F401
    INFO, ACHIEVEMENTS, RULES_TEXT, STATS_ROWS, create_run)
