"""Voxel Hell — bullet-hell invaders. Cabinet game module."""
from games.voxelhell.achievements import ACHIEVEMENTS  # noqa: F401
from games.voxelhell.game import INFO, create_run  # noqa: F401
from games.voxelhell.skins import (  # noqa: F401
    SKINS, SKIN_ORDER, skin_for_achievement,
)
from games.voxelhell.bot import demo_bot  # noqa: F401
