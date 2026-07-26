"""Cabinet Man's cabinet-level identity: attract-mode integration, persona
touches, and his own achievement set. Pure/headless logic here (no pygame,
no GL); main.py wires it into the attract loop, the takeover banner, and the
per-frame achievement check, mirroring how ambient mode's mood achievements
plug in via meta.achievements.evaluate_ambient.

The "attract star" decides who headlines an idle attract cycle:
  - "replays"     — always the canned demo bot (the historical behavior)
  - "cabinet_man" — always a live Cabinet Man pilot run (on an opted-in game)
  - "mixed"       — alternate canned / pilot cycles (the default once enough
                    pilots exist for it to feel varied)
A pilot can only star a cycle for a game that opts in (exports create_pilot);
if none do, every setting degrades gracefully to canned replays.
"""
from datetime import datetime, timezone


# Below this many opted-in pilots, "mixed" isn't worth it (too little variety)
# and even "cabinet_man" has nothing to show — both fall back to canned.
MIXED_MIN_PILOTS = 2

# Deterministic takeover-banner rotation — restraint over cringe (Emberlight
# warmth, no exclamation-point spam). Indexed by a summon counter.
TAKEOVER_BANNERS = [
    "CABINET MAN AT THE CONTROLS",
    "the house will take it from here",
    "watch this",
    "Cabinet Man is driving",
]

HANDBACK_BANNER = "…all yours"

# Attract caption shown while a pilot is starring the idle cycle.
ATTRACT_CAPTION = "CABINET MAN is playing — press any button"


def pilot_game_ids(games):
    """The game ids that have opted into Cabinet Man (export create_pilot),
    in registry order. `games` is the id -> module dict."""
    return [gid for gid, module in games.items()
            if getattr(module, "create_pilot", None) is not None]


def attract_star_is_pilot(star_setting, pilot_gids, cycle_index):
    """Whether a given attract cycle should be *starred* by a live pilot
    rather than the canned demo bot, given the `attract_star` setting, the
    available opted-in pilot game ids, and a monotonic cycle counter.

    - "replays": never a pilot.
    - "cabinet_man": always a pilot (when any exist).
    - "mixed": every other cycle is a pilot, but only once there are enough
      pilots for the variety to land; otherwise canned.
    Any setting degrades to canned when no pilots are available."""
    if not pilot_gids:
        return False
    if star_setting == "replays":
        return False
    if star_setting == "cabinet_man":
        return True
    if star_setting == "mixed":
        if len(pilot_gids) < MIXED_MIN_PILOTS:
            return False
        return cycle_index % 2 == 1
    return False


def pick_pilot_gid(pilot_gids, cycle_index):
    """Which opted-in pilot game stars this cycle — a deterministic rotation
    so attract cycles through the different pilots over time."""
    if not pilot_gids:
        return None
    return pilot_gids[cycle_index % len(pilot_gids)]


def takeover_banner(summon_count):
    """The takeover banner for the Nth summon (1-based), rotating through the
    variants deterministically."""
    n = max(0, summon_count - 1)
    return TAKEOVER_BANNERS[n % len(TAKEOVER_BANNERS)]


# --------------------------------------------------------- achievements
# Cabinet Man isn't a game, so his achievements are evaluated at the cabinet
# level against profile["cabinet_man"] counters + a live context, exactly
# like ambient's mood achievements (meta.achievements.evaluate_ambient).
CABINET_MAN_ACHIEVEMENTS = [
    ("ghost_in_the_machine", "Ghost in the Machine",
     "Summon Cabinet Man and watch him play for a full minute.",
     lambda c: c.get("watch_seconds", 0) >= 60),
    ("tag_team", "Tag Team",
     "Take back the controls from Cabinet Man and beat your session best "
     "anyway — all your own doing.",
     lambda c: c.get("beat_session_best_after_handback", False)),
]


def cabinet_man_section(profile):
    """Fetch (creating/backfilling) profile['cabinet_man']: the achievement
    unlocks + lifetime counters. Tolerant of saves that predate it."""
    cm = profile.setdefault("cabinet_man", {})
    cm.setdefault("achievements", {})
    counters = cm.setdefault("counters", {})
    counters.setdefault("summons", 0)
    counters.setdefault("longest_watch", 0.0)
    return cm


def evaluate_cabinet_man(profile, context):
    """Check the Cabinet Man achievements against `context` and record any new
    unlocks in profile['cabinet_man']['achievements']. Returns newly-unlocked
    (id, name, desc) tuples for toasting. Pure/headless — no GL. Mirrors
    meta.achievements.evaluate_ambient's shape so main.py wires it the same
    way."""
    cm = cabinet_man_section(profile)
    unlocked = cm["achievements"]
    out = []
    for aid, name, desc, predicate in CABINET_MAN_ACHIEVEMENTS:
        if aid in unlocked:
            continue
        try:
            hit = predicate(context)
        except (KeyError, TypeError):
            hit = False
        if hit:
            unlocked[aid] = {
                "unlocked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            out.append((aid, name, desc))
    return out
