"""Gin Rummy — solo vs a simple AI. Rules + meld engine in model.py; the
cabinet view + INFO in game.py.
"""
from games.rummy.model import GinRummy, best_deadwood, all_melds  # noqa: F401
from games.rummy.game import INFO, ACHIEVEMENTS, RULES_TEXT, create_run  # noqa: F401
