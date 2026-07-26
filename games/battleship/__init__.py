"""Battleship — hidden-information board game (BOARD category).

SECRET LOCAL mode: two players in one room, each on their own phone (a private
controller), with the cabinet as the shared TV. Rules in model.py, AI in
ai.py, cabinet view + secret/public projections in game.py.
"""
from games.battleship.achievements import ACHIEVEMENTS  # noqa: F401
from games.battleship.game import INFO, create_run  # noqa: F401
