"""Cosmetic skins for the tabletop suite — pure data + registry with unlock
gating. Two kinds, both shared across every tabletop game and stored globally
in profile["tabletop"]:

- DeckSkin: how a card looks — its geometric `back` pattern (see cards.render
  BACK_PATTERNS) and face/ink palette. `back_bg` optionally sets the back's base
  colour (defaults to a darkened trim); high-contrast light-backed decks set it.
- FeltSkin: the playmat. kind is "solid" | "gradient" | "pattern:<id>" |
  "scene:<ambient_scene>" (dynamic felts reuse the ambient scene renderers).

Premium skins carry an unlock achievement id (solitaire grind / flagship) and
are hidden by available_*(unlocked) until earned.
"""
from dataclasses import asdict, dataclass

from game import theme


def _rgb(c):
    return [c[0], c[1], c[2]]


# ------------------------------------------------------------------ decks
@dataclass
class DeckSkin:
    id: str
    name: str
    back: str            # back-pattern id (cards.render BACK_PATTERNS)
    face: list           # card face background [r,g,b]
    ink_black: list      # spades/clubs ink
    ink_red: list        # hearts/diamonds ink
    trim: list           # border + back pattern colour
    back_bg: list = None  # back base fill (defaults to darkened trim)
    premium: str = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], name=d["name"], back=d["back"],
                   face=list(d["face"]), ink_black=list(d["ink_black"]),
                   ink_red=list(d["ink_red"]), trim=list(d["trim"]),
                   back_bg=list(d["back_bg"]) if d.get("back_bg") else None,
                   premium=d.get("premium"))


_CREAM = _rgb(theme.CREAM)
_INK = [26, 20, 16]
_WHITE_INK = [238, 236, 232]
_RED = _rgb(theme.GARNET)

DECKS = [
    # --- light-faced classics (varied geometric backs) ---
    DeckSkin("classic", "Classic", "emblem", _CREAM, _INK, _RED, _rgb(theme.HONEY)),
    DeckSkin("parchment", "Parchment", "frames", [235, 222, 198], _INK,
             _rgb(theme.RUST), _rgb(theme.COPPER)),
    DeckSkin("lagoon", "Lagoon", "grid", _CREAM, _INK, _RED, _rgb(theme.LAGOON)),
    DeckSkin("garden", "Garden", "checker", _CREAM, [22, 44, 26], _RED,
             _rgb(theme.FERN)),
    DeckSkin("rose", "Rose", "dots", [245, 232, 236], _INK, _rgb(theme.PETAL),
             _rgb(theme.BLOOM)),
    DeckSkin("slate", "Slate", "brick", [214, 214, 222], _INK, _RED,
             _rgb(theme.STEEL)),
    DeckSkin("honey", "Honey", "diamond", [246, 232, 200], _INK, _rgb(theme.RUST),
             _rgb(theme.HONEY)),
    DeckSkin("iris", "Iris", "cross", [238, 232, 248], _INK, _rgb(theme.IRIS),
             _rgb(theme.IRIS)),
    DeckSkin("mint", "Mint", "dots", [224, 240, 230], [20, 40, 30], _RED,
             _rgb(theme.SAGE)),
    DeckSkin("bone", "Bone", "bars", [236, 230, 216], _INK, _rgb(theme.RUST),
             [70, 60, 50]),
    # --- high-contrast ---
    DeckSkin("contrast_light", "High Key", "grid", [245, 243, 239], [14, 12, 10],
             [150, 24, 30], [34, 30, 26], back_bg=[226, 222, 214]),
    DeckSkin("contrast_dark", "Low Key", "frames", [14, 14, 18], _WHITE_INK,
             _rgb(theme.EMBER), _rgb(theme.FROST), back_bg=[9, 9, 12]),
    # --- dark-faced ---
    DeckSkin("midnight", "Midnight", "pinstripe", [22, 26, 38], _rgb(theme.FROST),
             _rgb(theme.EMBER), _rgb(theme.COBALT), back_bg=[12, 14, 24]),
    DeckSkin("noir", "Noir", "brick", [20, 20, 24], [212, 212, 218],
             [222, 84, 84], _rgb(theme.STEEL), back_bg=[12, 12, 16]),
    DeckSkin("copperplate", "Copperplate", "diamond", [40, 28, 20],
             _rgb(theme.HONEY), _rgb(theme.EMBER), _rgb(theme.COPPER),
             back_bg=[22, 15, 10]),
    DeckSkin("pine", "Pine", "checker", [18, 30, 26], [210, 228, 216],
             _rgb(theme.PETAL), _rgb(theme.PINE), back_bg=[10, 20, 16]),
    # --- premium (unlocked by solitaire grind / flagship achievements) ---
    DeckSkin("ember_royale", "Ember Royale", "emblem", [40, 24, 18],
             _rgb(theme.HONEY), _rgb(theme.EMBER), _rgb(theme.GOLD),
             back_bg=[24, 14, 10], premium="first_win"),
    DeckSkin("neon", "Neon", "grid", [16, 18, 30], [120, 240, 200],
             [255, 120, 200], [120, 240, 200], back_bg=[10, 10, 20],
             premium="streak_3"),
    DeckSkin("galaxy_deck", "Galaxy", "dots", [18, 20, 34], _rgb(theme.FROST),
             _rgb(theme.BLOOM), _rgb(theme.IRIS), back_bg=[10, 12, 24],
             premium="century"),
    DeckSkin("gilded", "Gilded", "frames", [34, 28, 14], _rgb(theme.GOLD),
             _rgb(theme.EMBER), _rgb(theme.GOLD), back_bg=[20, 16, 8],
             premium="founder"),
    DeckSkin("void", "Void", "pinstripe", [12, 12, 16], _rgb(theme.STEEL),
             _rgb(theme.GARNET), _rgb(theme.COBALT), back_bg=[8, 8, 12],
             premium="millennium"),
    DeckSkin("juniper", "Juniper", "cross", _CREAM, [24, 32, 22], _RED,
             _rgb(theme.FERN), back_bg=[20, 28, 20], premium="first_gin"),
    DeckSkin("high_roller", "High Roller", "diamond", [18, 16, 12],
             _rgb(theme.GOLD), _RED, _rgb(theme.GOLD), back_bg=[10, 9, 7],
             premium="natural_royal"),
]


# ------------------------------------------------------------------ felts
@dataclass
class FeltSkin:
    id: str
    name: str
    kind: str            # "solid" | "gradient" | "pattern:<id>" | "scene:<id>"
    colors: list         # [[r,g,b], ...] (base first; pattern/gradient use more)
    premium: str = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], name=d["name"], kind=d["kind"],
                   colors=[list(c) for c in d["colors"]],
                   premium=d.get("premium"))

    @property
    def scene(self):
        return self.kind.split(":", 1)[1] if self.kind.startswith("scene:") else None

    @property
    def pattern(self):
        return self.kind.split(":", 1)[1] if self.kind.startswith("pattern:") else None


FELTS = [
    # solids (neutral + high-contrast)
    FeltSkin("classic_green", "Classic Green", "gradient",
             [[24, 66, 44], [16, 44, 30]]),
    FeltSkin("emberlight", "Emberlight", "gradient",
             [[38, 26, 18], [20, 13, 9]]),
    FeltSkin("midnight", "Midnight", "solid", [[16, 20, 34]]),
    FeltSkin("slate", "Slate", "solid", [[30, 32, 38]]),
    FeltSkin("charcoal", "Charcoal", "solid", [[16, 16, 20]]),
    FeltSkin("ink", "Ink", "solid", [[9, 9, 13]]),
    FeltSkin("bone", "Bone", "solid", [[210, 202, 184]]),
    FeltSkin("teal", "Teal", "solid", [[16, 42, 46]]),
    FeltSkin("plum", "Plum", "solid", [[40, 20, 44]]),
    # gradients
    FeltSkin("wine", "Wine", "gradient", [[58, 20, 30], [30, 12, 18]]),
    FeltSkin("forest", "Forest", "gradient", [[20, 44, 30], [12, 26, 20]]),
    FeltSkin("dusk", "Dusk", "gradient", [[58, 36, 20], [22, 15, 10]]),
    FeltSkin("ocean", "Ocean", "gradient", [[20, 40, 70], [10, 18, 34]]),
    # geometric patterns
    FeltSkin("carbon", "Carbon", "pattern:carbon", [[18, 18, 22], [40, 40, 48]]),
    FeltSkin("baize", "Baize Grid", "pattern:grid", [[16, 44, 30], [28, 64, 44]]),
    FeltSkin("checkerboard", "Checkerboard", "pattern:checker",
             [[22, 24, 30], [34, 36, 44]]),
    FeltSkin("polka", "Polka", "pattern:dots", [[26, 18, 12], [58, 40, 24]]),
    # dynamic (living ambient-scene backdrops)
    FeltSkin("galaxy", "Galaxy", "scene:nebula",
             [_rgb(theme.IRIS), _rgb(theme.BLOOM), _rgb(theme.COBALT)]),
    FeltSkin("aurora", "Aurora", "scene:aurora",
             [_rgb(theme.SAGE), _rgb(theme.LAGOON), _rgb(theme.IRIS)]),
    FeltSkin("hearth", "Hearth", "scene:embers",
             [_rgb(theme.EMBER), _rgb(theme.COPPER), _rgb(theme.HONEY)]),
    FeltSkin("matrix", "Matrix", "scene:lattice",
             [_rgb(theme.SAGE), _rgb(theme.FROST), _rgb(theme.LAGOON)]),
    # premium dynamic felts
    FeltSkin("starlit", "Starlit", "scene:starfield",
             [_rgb(theme.FROST), _rgb(theme.COBALT), _rgb(theme.CREAM)],
             premium="century"),
    FeltSkin("inferno", "Inferno", "scene:fireplace",
             [_rgb(theme.EMBER), _rgb(theme.RUST), _rgb(theme.GARNET)],
             premium="millennium"),
    FeltSkin("prism", "Prism", "scene:lattice",
             [_rgb(theme.IRIS), _rgb(theme.PETAL), _rgb(theme.FROST)],
             premium="streak_3"),
    FeltSkin("speakeasy", "Speakeasy", "pattern:carbon",
             [[30, 20, 14], _rgb(theme.HONEY)], premium="game_win"),
    FeltSkin("casino_floor", "Casino Floor", "pattern:dots",
             [[46, 12, 16], _rgb(theme.GOLD)], premium="quads"),
]


# ------------------------------------------------------------------ boards
@dataclass
class BoardSkin:
    """A Backgammon board + checker palette — a third tabletop cosmetic
    category alongside decks/felts, since the board isn't cards."""
    id: str
    name: str
    point_light: list
    point_dark: list
    frame: list
    checker_a: list
    checker_b: list
    checker_trim: list
    premium: str = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], name=d["name"],
                   point_light=list(d["point_light"]), point_dark=list(d["point_dark"]),
                   frame=list(d["frame"]), checker_a=list(d["checker_a"]),
                   checker_b=list(d["checker_b"]), checker_trim=list(d["checker_trim"]),
                   premium=d.get("premium"))


BOARDS = [
    BoardSkin("emberlight_walnut", "Emberlight Walnut", [74, 52, 36], [52, 36, 24],
             _rgb(theme.COPPER), _rgb(theme.EMBER), _rgb(theme.FROST), [16, 12, 10]),
    BoardSkin("classic_tan", "Classic Tan", [196, 164, 120], [140, 100, 64],
             [90, 60, 30], [40, 40, 44], [230, 230, 236], [16, 12, 10]),
    BoardSkin("midnight", "Midnight", [30, 32, 44], [18, 18, 26],
             _rgb(theme.COBALT), _rgb(theme.FROST), _rgb(theme.GARNET), [8, 8, 12]),
    BoardSkin("contrast", "High Key", [232, 228, 220], [180, 176, 168],
             [20, 20, 20], [20, 20, 24], [200, 30, 40], [10, 10, 10]),
    BoardSkin("frost", "Frost", [210, 222, 232], [170, 188, 204],
             _rgb(theme.COBALT), _rgb(theme.COBALT), _rgb(theme.EMBER), [30, 30, 40]),
    BoardSkin("garden", "Garden", [200, 220, 190], [150, 180, 140],
             _rgb(theme.FERN), _rgb(theme.RUST), _rgb(theme.SAGE), [20, 30, 20]),
    # premium (unlocked by backgammon achievements)
    BoardSkin("noir_lacquer", "Noir Lacquer", [22, 20, 24], [12, 10, 14],
             _rgb(theme.GOLD), _rgb(theme.GOLD), _rgb(theme.FROST), [8, 8, 10],
             premium="gammon"),
    BoardSkin("royal_marble", "Royal Marble", [230, 224, 236], [200, 190, 214],
             _rgb(theme.IRIS), _rgb(theme.IRIS), _rgb(theme.GOLD), [30, 20, 10],
             premium="bg_wins_50"),
]


# ---------------------------------------------------------------- registry
def _avail(items, unlocked):
    unlocked = unlocked or set()
    return [it for it in items if it.premium is None or it.premium in unlocked]


def available_decks(unlocked):
    return _avail(DECKS, unlocked)


def available_felts(unlocked):
    return _avail(FELTS, unlocked)


def available_boards(unlocked):
    return _avail(BOARDS, unlocked)


def deck_by_id(deck_id):
    for d in DECKS:
        if d.id == deck_id:
            return d
    return DECKS[0]


def felt_by_id(felt_id):
    for f in FELTS:
        if f.id == felt_id:
            return f
    return FELTS[0]


def board_by_id(board_id):
    for b in BOARDS:
        if b.id == board_id:
            return b
    return BOARDS[0]
