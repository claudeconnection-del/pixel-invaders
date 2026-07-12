"""Emberlight — the cabinet's shared visual theme.

One warm palette lit like firelight against a deep, cozy dark. Every screen
and every game draws from this so the cabinet reads as one family; each game
then claims a *signature accent* from the same 16-colour set for character.

Colours are RGBA 0-255 tuples (what render.text's overlay expects). For voxel
tints — which multiply a sprite's own vertex colour and may exceed 1.0 to glow
— use voxel()/stud() to convert a named colour to a 0-1 (optionally hot) tint.

Design tokens, not magic numbers: reach for the *semantic* names (TEXT, DIM,
SCORE, GOLD, WARN, PANEL, ...) in shared UI, and a game's Theme.accent for its
own colour. Keep the personal brand out of the bytes — the anonymised
Emberlight identity (name, spark/crescent marks, "the light stays on") is fine;
domains are not.
"""

# --------------------------------------------------------------- palette 16
# Named after the Emberlight brand kit; the light, the candle, the cosmos.
EMBER = (238, 169, 76, 255)      # the light / primary call-to-action
HONEY = (236, 194, 96, 255)      # candle gold — medals, multipliers
CHAMPAGNE = (231, 214, 166, 255)  # pale toast — soft highlight
COPPER = (221, 126, 75, 255)     # autumn flame
RUST = (217, 99, 90, 255)        # warm warning
GARNET = (200, 79, 99, 255)      # deep red — danger
BLOOM = (255, 108, 174, 255)     # play — hot pink
PETAL = (240, 168, 192, 255)     # soft pink
IRIS = (180, 135, 230, 255)      # cosmos violet
STEEL = (142, 130, 176, 255)     # quiet violet-grey
COBALT = (122, 143, 222, 255)    # night blue
FROST = (165, 198, 232, 255)     # ice
LAGOON = (86, 184, 178, 255)     # teal
SAGE = (99, 200, 166, 255)       # all is well
FERN = (134, 193, 120, 255)      # clover
PINE = (78, 143, 107, 255)       # evergreen

# ------------------------------------------------------------- neutral ink
CREAM = (243, 231, 212, 255)     # primary text, on the warm dark
TAUPE = (171, 152, 128, 255)     # secondary/dim text — warm grey, still legible
FAINT = (112, 99, 84, 255)       # hairlines, locked/inert marks

# --------------------------------------------------------- semantic aliases
# Shared across every screen so the cabinet stays one system.
TEXT = CREAM                     # body/foreground text
DIM = TAUPE                      # captions, inactive rows, hints
PRIMARY = EMBER                  # the house colour: titles, score, confirms
SCORE = EMBER                    # score readouts (same everywhere on purpose)
GOLD = HONEY                     # best score, multiplier, "equipped"
WARN = RUST                      # caution states
DANGER = GARNET                  # loss, low health, "locked"
GOOD = SAGE                      # success, "all clear"
INFO = FROST                     # neutral informational accent

# ------------------------------------------------------------ dark surfaces
SCENE_CLEAR = (0.055, 0.035, 0.026)  # GL clear: warm near-black (firelit room)
PANEL = (26, 18, 13, 222)        # menu/HUD panels
PANEL_DIM = (20, 14, 10, 205)    # empty/quiet panels
PANEL_SEL = (56, 41, 27, 168)    # selected-row wash
BAR_BG = (56, 43, 30, 224)       # meter / progress tracks
HAIR = (74, 61, 48, 255)         # faint separators, locked edges

# ------------------------------------------------------------- tint helpers


def voxel(color, k=1.0):
    """Named colour -> (r, g, b) 0-1 voxel tint. k>1 glows (emissive)."""
    return (color[0] / 255 * k, color[1] / 255 * k, color[2] / 255 * k)


def stud(color, k=0.85, a=0.55):
    """Named colour -> (r, g, b, a) tint for a white cube used as a marker."""
    r, g, b = voxel(color, k)
    return (r, g, b, a)


# --------------------------------------------------- warm starfield / sparks
# The drifting backdrop stars, warmed: mostly firelight, a few cool embers of
# distance for depth. (renderer builds the array; these seed its colours.)
STAR_WARM = (1.0, 0.82, 0.55)    # ember/honey majority
STAR_COOL = (0.72, 0.78, 1.0)    # occasional cool star, for contrast


class Theme:
    """A game's signature within the family. accent/accent2 are RGBA overlay
    colours; scene() gives the field-marker (arena stud) tint."""

    __slots__ = ("accent", "accent2", "stud_color")

    def __init__(self, accent, accent2, stud_color=None):
        self.accent = accent
        self.accent2 = accent2
        self.stud_color = stud_color or accent

    def scene_studs(self, k=0.8, a=0.5):
        return stud(self.stud_color, k, a)


# Curated per-game signatures — all from the palette above, so distinct yet
# harmonised. Ember stays the shared house colour (score/confirm) everywhere.
GAMES = {
    "voxelhell": Theme(IRIS, BLOOM, IRIS),        # cosmos bullet-hell
    "breaker":   Theme(LAGOON, FROST, LAGOON),    # cool crystal demolition
    "serpent":   Theme(FERN, SAGE, PINE),         # garden green
    "voxeldoom": Theme(GARNET, RUST, GARNET),     # hell-red dungeon
    "crisis":    Theme(COPPER, EMBER, COPPER),    # dusk on-rails
    "aimtrainer": Theme(FROST, COBALT, COBALT),   # cool precision range
    "studio":    Theme(BLOOM, PETAL, BLOOM),      # creative pink
}

DEFAULT = Theme(EMBER, HONEY, EMBER)


def for_game(gid):
    return GAMES.get(gid, DEFAULT)
