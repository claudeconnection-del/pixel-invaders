"""Cosmetic skins for the tabletop suite — pure data + registry with unlock
gating. Two kinds, both shared across every tabletop game and stored globally
in profile["tabletop"]:

- DeckSkin: how a card looks — its back pattern and face/ink palette.
- FeltSkin: the playmat. kind is "solid" | "gradient" | "scene:<ambient_scene>"
  (dynamic felts reuse the ambient scene renderers as a living backdrop).

Premium skins carry an unlock achievement id (solitaire grind or flagship) and
are hidden by available_*(unlocked) until earned — same mechanism as elsewhere.
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
    back: str            # back-pattern id (render.py interprets)
    face: list           # card face background [r,g,b]
    ink_black: list      # spades/clubs ink
    ink_red: list        # hearts/diamonds ink
    trim: list           # card border / rounded edge
    premium: str = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in
                      ("id", "name", "back", "face", "ink_black", "ink_red",
                       "trim")}, premium=d.get("premium"))


_CREAM = _rgb(theme.CREAM)
_INK = [26, 20, 16]
_RED = _rgb(theme.GARNET)
_DARKFACE = [26, 30, 40]
_LIGHTINK = _rgb(theme.FROST)

DECKS = [
    DeckSkin("classic", "Classic", "ember", _CREAM, _INK, _RED, _rgb(theme.HONEY)),
    DeckSkin("parchment", "Parchment", "lattice", [235, 222, 198], _INK,
             _rgb(theme.RUST), _rgb(theme.COPPER)),
    DeckSkin("lagoon", "Lagoon", "waves", _CREAM, _INK, _RED, _rgb(theme.LAGOON)),
    DeckSkin("garden", "Garden", "diamond", _CREAM, [24, 40, 24], _RED,
             _rgb(theme.FERN)),
    DeckSkin("rose", "Rose", "bloom", [245, 232, 236], _INK, _rgb(theme.PETAL),
             _rgb(theme.BLOOM)),
    DeckSkin("slate", "Slate", "circuit", [214, 214, 222], _INK, _RED,
             _rgb(theme.STEEL)),
    DeckSkin("honey", "Honey", "ember", [246, 232, 200], _INK, _rgb(theme.RUST),
             _rgb(theme.HONEY)),
    DeckSkin("midnight", "Midnight", "starfield", _DARKFACE, _LIGHTINK,
             _rgb(theme.EMBER), _rgb(theme.COBALT)),
    DeckSkin("iris", "Iris", "lattice", [238, 232, 248], _INK, _rgb(theme.IRIS),
             _rgb(theme.IRIS)),
    # premium — unlocked by solitaire grind / flagship achievements
    DeckSkin("ember_royale", "Ember Royale", "ember", [40, 24, 18],
             _rgb(theme.HONEY), _rgb(theme.EMBER), _rgb(theme.GOLD),
             premium="first_win"),
    DeckSkin("galaxy_deck", "Galaxy", "starfield", [18, 20, 34],
             _rgb(theme.FROST), _rgb(theme.BLOOM), _rgb(theme.IRIS),
             premium="century"),
    DeckSkin("gilded", "Gilded", "diamond", [34, 28, 14], _rgb(theme.GOLD),
             _rgb(theme.EMBER), _rgb(theme.GOLD), premium="founder"),
    DeckSkin("void", "Void", "circuit", [14, 14, 18], _rgb(theme.STEEL),
             _rgb(theme.GARNET), _rgb(theme.COBALT), premium="millennium"),
]


# ------------------------------------------------------------------ felts
@dataclass
class FeltSkin:
    id: str
    name: str
    kind: str            # "solid" | "gradient" | "scene:<ambient_scene_id>"
    colors: list         # [[r,g,b], ...] (1 solid, 2 gradient; scene: palette)
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
        """The ambient scene id for a dynamic felt, else None."""
        return self.kind.split(":", 1)[1] if self.kind.startswith("scene:") else None


FELTS = [
    FeltSkin("classic_green", "Classic Green", "gradient",
             [[24, 66, 44], [16, 44, 30]]),
    FeltSkin("emberlight", "Emberlight", "gradient",
             [[38, 26, 18], [20, 13, 9]]),
    FeltSkin("midnight", "Midnight", "solid", [[16, 20, 34]]),
    FeltSkin("wine", "Wine", "gradient", [[58, 20, 30], [30, 12, 18]]),
    FeltSkin("slate", "Slate", "solid", [[30, 32, 38]]),
    FeltSkin("forest", "Forest", "gradient", [[20, 44, 30], [12, 26, 20]]),
    # dynamic / themed felts — living ambient-scene backdrops
    FeltSkin("galaxy", "Galaxy", "scene:nebula",
             [_rgb(theme.IRIS), _rgb(theme.BLOOM), _rgb(theme.COBALT)]),
    FeltSkin("aurora", "Aurora", "scene:aurora",
             [_rgb(theme.SAGE), _rgb(theme.LAGOON), _rgb(theme.IRIS)]),
    FeltSkin("hearth", "Hearth", "scene:embers",
             [_rgb(theme.EMBER), _rgb(theme.COPPER), _rgb(theme.HONEY)]),
    # premium dynamic felts
    FeltSkin("starlit", "Starlit", "scene:starfield",
             [_rgb(theme.FROST), _rgb(theme.COBALT), _rgb(theme.CREAM)],
             premium="century"),
    FeltSkin("inferno", "Inferno", "scene:fireplace",
             [_rgb(theme.EMBER), _rgb(theme.RUST), _rgb(theme.GARNET)],
             premium="millennium"),
]


# ---------------------------------------------------------------- registry
def _avail(items, unlocked):
    unlocked = unlocked or set()
    return [it for it in items if it.premium is None or it.premium in unlocked]


def available_decks(unlocked):
    return _avail(DECKS, unlocked)


def available_felts(unlocked):
    return _avail(FELTS, unlocked)


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
