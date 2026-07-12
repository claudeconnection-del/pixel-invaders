"""Single source of truth for all pixel-grid art.

Every sprite is a list of equal-length strings; each character indexes PALETTE.
The PNG baker (tools/gen_art.py) rasterizes these for docs/2D use, and the voxel
renderer (render/voxel.py) extrudes them into cube meshes for the 3D game.
"""

TRANSPARENT = (0, 0, 0, 0)

PALETTE = {
    ".": TRANSPARENT,
    "G": (80, 220, 120, 255),    # green
    "g": (140, 255, 170, 255),   # bright green
    "M": (230, 80, 200, 255),    # magenta
    "m": (255, 150, 230, 255),   # bright magenta
    "C": (80, 200, 230, 255),    # cyan
    "c": (160, 240, 255, 255),   # bright cyan
    "W": (240, 240, 240, 255),   # white
    "Y": (250, 220, 90, 255),    # yellow
    "y": (255, 245, 180, 255),   # pale yellow
    "O": (250, 150, 60, 255),    # orange
    "R": (230, 60, 60, 255),     # red
    "r": (255, 130, 120, 255),   # bright red
    "#": (120, 120, 130, 255),   # grey
    "P": (150, 80, 220, 255),    # purple
    "p": (200, 150, 255, 255),   # bright purple
    "D": (235, 190, 60, 255),    # gold
    "d": (170, 130, 30, 255),    # dark gold
    "B": (70, 110, 230, 255),    # blue
    "b": (140, 180, 255, 255),   # bright blue
}

# ---------------------------------------------------------------- player skins
SHIP_VANGUARD = [
    "...W....",
    "..WWW...",
    "..WWW...",
    ".WWWWW..",
    "WWWWWWW.",
    "WWWWWWW.",
    "W.W.W.W.",
    "W.....W.",
]

SHIP_RAIDER = [
    "M......M",
    "MM....MM",
    "MMm..mMM",
    "MMMMMMMM",
    "mMMMMMMm",
    "MM.MM.MM",
    "M..mm..M",
    "...MM...",
]

SHIP_DART = [
    "...C....",
    "...c....",
    "..CcC...",
    "..CcC...",
    ".CCcCC..",
    ".CCcCC..",
    "CC.C.CC.",
    ".C...C..",
]

SHIP_GOLD_ACE = [
    "...D....",
    "..DdD...",
    ".DDdDD..",
    "DDDdDDD.",
    "DdDDDdD.",
    "DD.D.DD.",
    "D.DDD.D.",
    "..D.D...",
]

SHIP_GHOST = [
    "...W....",
    "..W#W...",
    ".W###W..",
    ".WWWWW..",
    "W#WWW#W.",
    "WW.W.WW.",
    "W.....W.",
    "........",
]

SHIP_PRISMATIC = [
    "...W....",
    "..WWW...",
    ".W#W#W..",
    "WWWWWWW.",
    "W#WWW#W.",
    "WWW.WWW.",
    "W.W.W.W.",
    ".W...W..",
]

# ------------------------------------------------------------------- enemies
ENEMY_SQUID_A = [
    "..C....C",
    "...CCCC.",
    "..CcccC.",
    ".CCcccCC",
    "CCCCCCCC",
    "..C..C..",
    ".C.CC.C.",
    "C.C..C.C",
]
ENEMY_SQUID_B = [
    "..C....C",
    "...CCCC.",
    "..CcccC.",
    ".CCcccCC",
    "CCCCCCCC",
    ".C.CC.C.",
    "C.C..C.C",
    "..C..C..",
]

ENEMY_CRAB_A = [
    ".M.....M",
    "..M...M.",
    ".MMMMMMM",
    "MMmMMmMM",
    "MMMMMMMM",
    "..M.M.M.",
    ".M.M.M.M",
    "M.M...M.",
]
ENEMY_CRAB_B = [
    ".M.....M",
    "M.M...M.",
    "MMMMMMMM",
    "MMmMMmMM",
    ".MMMMMMM",
    "..M.M.M.",
    ".M.M.M.M",
    "..M...M.",
]

ENEMY_OCTO_A = [
    "..GGGG..",
    ".GGGGGG.",
    "GGgGGgGG",
    "GGGGGGGG",
    ".GGGGGG.",
    "..G..G..",
    ".G.GG.G.",
    "G.G..G.G",
]
ENEMY_OCTO_B = [
    "..GGGG..",
    ".GGGGGG.",
    "GGgGGgGG",
    "GGGGGGGG",
    ".GGGGGG.",
    "..GGGG..",
    ".G.GG.G.",
    "..G..G..",
]

# Elite enemy for later waves: armored diamond
ENEMY_ELITE_A = [
    "...BB...",
    "..BbbB..",
    ".BbWWbB.",
    "BbWBBWbB",
    "BbWBBWbB",
    ".BbWWbB.",
    "..BbbB..",
    "...BB...",
]
ENEMY_ELITE_B = [
    "...BB...",
    "..BWWB..",
    ".BWbbWB.",
    "BWbBBbWB",
    "BWbBBbWB",
    ".BWbbWB.",
    "..BWWB..",
    "...BB...",
]

# ---------------------------------------------------------------------- boss
BOSS = [
    "....PPPPPPPP....",
    "..PPPPPPPPPPPP..",
    ".PPPpPPPPpPPPP..",
    ".PPppPPPPppPPP..",
    "PPPPPPPPPPPPPPPP",
    "PPPWWPPPPPPWWPPP",
    "PPWRRWPPPPWRRWPP",
    "PPPWWPPPPPPWWPPP",
    "PPPPPPPPPPPPPPPP",
    ".PPpPPpPPpPPpPP.",
    "..P.PP.PP.PP.P..",
    ".P...P....P...P.",
]

# ------------------------------------------------------------------- bullets
BULLET_PLAYER = [
    "W",
    "W",
    "W",
    "W",
]

BULLET_ENEMY = [
    ".Y.",
    "Y.Y",
    ".Y.",
    "Y.Y",
]

BULLET_ORB = [
    ".rr.",
    "ryyr",
    "ryyr",
    ".rr.",
]

BULLET_WALL = [
    "pp",
    "PP",
    "PP",
    "pp",
]

# ------------------------------------------------------------------ pickups
POWERUP_SPREAD = [
    "G....G",
    ".G..G.",
    "..GG..",
    "..gg..",
    ".g..g.",
    "g....g",
]

POWERUP_RAPID = [
    "...YY.",
    "..YY..",
    ".YYYY.",
    "...YY.",
    "..YY..",
    ".YY...",
]

POWERUP_SHIELD = [
    ".BBBB.",
    "BbbbbB",
    "Bb..bB",
    "Bb..bB",
    ".BbbbB",
    "..BB..",
]

# ------------------------------------------------------------------ breaker
PADDLE = [
    "cCCCCCCCCc",
    "CWWWWWWWWC",
    "cCCCCCCCCc",
]

BRICK = [
    "WWWWWW",
    "W####W",
    "WWWWWW",
]

# -------------------------------------------------------------------- misc
EXPLOSION = [
    "O.....O.",
    ".O...O..",
    "..OYO...",
    ".OYYYO..",
    "..OYO...",
    ".O...O..",
    "O.....O.",
    "........",
]


def grid_size(grid):
    return len(grid[0]), len(grid)


# name -> grid, used by the PNG baker and anywhere art is enumerated
ALL_SPRITES = {
    "ship_vanguard": SHIP_VANGUARD,
    "ship_raider": SHIP_RAIDER,
    "ship_dart": SHIP_DART,
    "ship_gold_ace": SHIP_GOLD_ACE,
    "ship_ghost": SHIP_GHOST,
    "ship_prismatic": SHIP_PRISMATIC,
    "enemy_squid_a": ENEMY_SQUID_A,
    "enemy_squid_b": ENEMY_SQUID_B,
    "enemy_crab_a": ENEMY_CRAB_A,
    "enemy_crab_b": ENEMY_CRAB_B,
    "enemy_octo_a": ENEMY_OCTO_A,
    "enemy_octo_b": ENEMY_OCTO_B,
    "enemy_elite_a": ENEMY_ELITE_A,
    "enemy_elite_b": ENEMY_ELITE_B,
    "boss": BOSS,
    "bullet_player": BULLET_PLAYER,
    "bullet_enemy": BULLET_ENEMY,
    "bullet_orb": BULLET_ORB,
    "bullet_wall": BULLET_WALL,
    "powerup_spread": POWERUP_SPREAD,
    "powerup_rapid": POWERUP_RAPID,
    "powerup_shield": POWERUP_SHIELD,
    "paddle": PADDLE,
    "brick": BRICK,
    "explosion": EXPLOSION,
}
