"""Backgammon — headless rules + AI core (CAB-10). Cabinet view/table
registration (board + checker skins, INFO/create_run, games/__init__.py
wiring) is a later increment (CAB-11); nothing here is registered yet.
"""
from games.backgammon.model import Backgammon, PLAYERS, OTHER  # noqa: F401
from games.backgammon.ai import ai_move, random_move  # noqa: F401
