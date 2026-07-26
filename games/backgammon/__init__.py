"""Backgammon — solo vs a simple AI. Rules + AI in model.py/ai.py; the
cabinet view + INFO in game.py. Board/checker skins are a later increment
(CAB-12).
"""
from games.backgammon.model import Backgammon, PLAYERS, OTHER  # noqa: F401
from games.backgammon.ai import ai_move, random_move  # noqa: F401
from games.backgammon.game import INFO, ACHIEVEMENTS, create_run  # noqa: F401
