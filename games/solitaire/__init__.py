"""Solitaire (Klondike) — the first tabletop game. Rules in model.py; the
cabinet view + INFO in game.py; achievements arrive in a later increment.
"""
from games.solitaire.model import Solitaire  # noqa: F401
from games.solitaire.game import (  # noqa: F401
    INFO, ACHIEVEMENTS, RULES_TEXT, create_run, create_pilot)
