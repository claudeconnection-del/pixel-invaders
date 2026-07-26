"""Cabinet-wide achievement completion — the collector's view.

Each game shows its own achievements in isolation; this rolls every source
up into a single "how far through EVERYTHING am I?" figure: the per-game
achievement modules plus the two cabinet-level sets (ambient mood, Cabinet
Man). Pure/read-only — it never spawns or mutates profile sections, so it's
safe to call every frame while drawing.
"""


def _earned(recorded, ids):
    """How many of `ids` this section has actually recorded, so stale or
    unknown ids left in a save never inflate the count past the module total."""
    return sum(1 for i in ids if i in recorded)


def _section_achievements(profile, *path):
    """Read profile[...path...]['achievements'] without creating anything."""
    node = profile
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return {}
    got = node.get("achievements") if isinstance(node, dict) else None
    return got if isinstance(got, dict) else {}


def completion(profile, modules):
    """Roll achievement progress up across the whole cabinet.

    `modules` is {gid: module}, each module exposing `.ACHIEVEMENTS` (a list
    of objects with an `.id`). Returns::

        {"total": (earned, total),
         "per_game": {gid: (earned, total)},
         "ambient": (earned, N),
         "cabinet_man": (earned, M)}

    where each `earned` intersects the ids the profile has recorded with the
    ids that source actually defines. Read-only.
    """
    from ambient.preset import AMBIENT_ACHIEVEMENTS
    from arcade.cabinet_man import CABINET_MAN_ACHIEVEMENTS

    per_game = {}
    tot_earned = tot_total = 0
    for gid, module in modules.items():
        ids = [a.id for a in getattr(module, "ACHIEVEMENTS", [])]
        recorded = _section_achievements(profile, "games", gid)
        earned = _earned(recorded, ids)
        per_game[gid] = (earned, len(ids))
        tot_earned += earned
        tot_total += len(ids)

    amb_ids = [a[0] for a in AMBIENT_ACHIEVEMENTS]
    amb = (_earned(_section_achievements(profile, "ambient"), amb_ids),
           len(amb_ids))

    cm_ids = [a[0] for a in CABINET_MAN_ACHIEVEMENTS]
    cm = (_earned(_section_achievements(profile, "cabinet_man"), cm_ids),
          len(cm_ids))

    tot_earned += amb[0] + cm[0]
    tot_total += amb[1] + cm[1]

    return {"total": (tot_earned, tot_total), "per_game": per_game,
            "ambient": amb, "cabinet_man": cm}


def percent(earned, total):
    """Integer completion percentage, 0 when nothing is defined yet."""
    return round(100 * earned / total) if total else 0


def completion_line(comp):
    """The one-line header/footer summary: "CABINET 12/47 · 26%"."""
    earned, total = comp["total"]
    return f"CABINET {earned}/{total} · {percent(earned, total)}%"
