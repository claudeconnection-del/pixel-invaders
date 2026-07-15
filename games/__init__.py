"""Cabinet game registry: categories and carousel order."""
import importlib

CATEGORIES = [
    ("CLASSICS +", ["voxelhell", "breaker", "serpent", "studio"]),
    ("FPS", ["voxeldoom", "crisis", "aimtrainer"]),
    ("BOARD", ["battleship"]),
    ("TABLETOP", ["solitaire"]),
]

GAME_IDS = [gid for _, ids in CATEGORIES for gid in ids]


def category_of(gid):
    for name, ids in CATEGORIES:
        if gid in ids:
            return name
    return CATEGORIES[0][0]


def games_in_category(name):
    for cat_name, ids in CATEGORIES:
        if cat_name == name:
            return ids
    return CATEGORIES[0][1]


def load_games():
    """Import every registered game module, keyed by id."""
    return {gid: importlib.import_module(f"games.{gid}") for gid in GAME_IDS}
