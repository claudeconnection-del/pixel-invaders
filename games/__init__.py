"""Cabinet game registry: every playable game, in carousel order."""
import importlib

GAME_IDS = ["voxelhell"]


def load_games():
    """Import every registered game module, keyed by id."""
    return {gid: importlib.import_module(f"games.{gid}") for gid in GAME_IDS}
