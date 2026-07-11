"""Player ship skins: each is distinct pixel art with an unlock condition."""

SKINS = {
    "vanguard": {
        "name": "Vanguard",
        "sprite": "ship_vanguard",
        "desc": "The original. Reliable, boxy, beloved.",
        "unlock": None,  # default
        "special": None,
    },
    "raider": {
        "name": "Raider",
        "sprite": "ship_raider",
        "desc": "Wide-wing interceptor in hostile magenta.",
        "unlock": "warmed_up",
        "special": None,
    },
    "dart": {
        "name": "Dart",
        "sprite": "ship_dart",
        "desc": "Slim profile. Built for threading needles.",
        "unlock": "graze_addict",
        "special": None,
    },
    "gold_ace": {
        "name": "Gold Ace",
        "sprite": "ship_gold_ace",
        "desc": "Trophy plating for boss slayers.",
        "unlock": "boss_slayer",
        "special": None,
    },
    "ghost": {
        "name": "Ghost",
        "sprite": "ship_ghost",
        "desc": "Semi-phased hull. They can't hit what they can barely see.",
        "unlock": "untouchable",
        "special": "translucent",
    },
    "prismatic": {
        "name": "Prismatic",
        "sprite": "ship_prismatic",
        "desc": "One credit. Zero deaths. Infinite colors.",
        "unlock": "one_credit_clear",
        "special": "hue_cycle",
    },
}

SKIN_ORDER = list(SKINS.keys())


def skin_for_achievement(achievement_id):
    for skin_id, skin in SKINS.items():
        if skin["unlock"] == achievement_id:
            return skin_id
    return None
