"""Headless meta-layer tests: per-game stats, achievements, skin unlocks,
profile v1->v2 migration, and save/load round-trip.

Run with: python tools/test_meta.py
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.voxelhell import ACHIEVEMENTS, skin_for_achievement  # noqa: E402
from games.voxelhell.world import World  # noqa: E402
from meta import profile as profile_mod  # noqa: E402
from meta import replay as replay_mod  # noqa: E402
from meta.achievements import AchievementEngine  # noqa: E402
from meta.stats import StatsTracker  # noqa: E402
from tools.test_world import dodge_bot_input, DT  # noqa: E402


def run_campaign_with_meta():
    profile = profile_mod.load(path="/nonexistent/so/defaults/load")
    section = profile_mod.game_section(profile, "voxelhell")
    stats = StatsTracker(section)
    engine = AchievementEngine(section, ACHIEVEMENTS, skin_for_achievement)

    world = World(rng=random.Random(1234), mode="campaign")
    world.player.lives = 99
    unlocked = []
    frames = 0
    while world.loop == 1 and not world.run_over and frames < 60 * 60 * 12:
        world.update(DT, dodge_bot_input(world))
        frame_events = world.drain_events()
        stats.on_frame(DT, frame_events)
        unlocked += engine.on_frame(frame_events, world.stats)
        frames += 1

    # die to finish the run (win, since loop 1 cleared)
    world.player.lives = 1
    from game.entities import InputState
    while not world.run_over and frames < 60 * 60 * 14:
        world.update(DT, InputState())
        frame_events = world.drain_events()
        stats.on_frame(DT, frame_events)
        unlocked += engine.on_frame(frame_events, world.stats)
        frames += 1

    ids = {a.id for a in unlocked}
    for expected in ("first_blood", "warmed_up", "halfway_there", "boss_slayer"):
        assert expected in ids, f"expected achievement {expected}, got {ids}"
    # bot takes hits during the campaign, so the no-death clear must NOT unlock
    assert "one_credit_clear" not in ids
    assert len(ids) == len(unlocked), "duplicate achievement unlocks"

    life = section["lifetime"]
    assert life["runs"] == 1 and life["wins"] == 1
    assert life["kills"] > 0 and life["bosses"] == 1
    assert life["best_score"] == world.score
    assert life["playtime"] > 0

    assert "raider" in section["unlocked_skins"]      # warmed_up
    assert "gold_ace" in section["unlocked_skins"]    # boss_slayer

    print(f"meta campaign OK: achievements={sorted(ids)}")
    print(f"  skins unlocked={section['unlocked_skins']}")
    return profile


def round_trip(profile):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "profile.json")
        profile_mod.save(profile, path=path)
        loaded = profile_mod.load(path=path)
        assert loaded["games"]["voxelhell"]["lifetime"] == \
            profile["games"]["voxelhell"]["lifetime"]
        assert loaded["games"]["voxelhell"]["achievements"].keys() == \
            profile["games"]["voxelhell"]["achievements"].keys()

        # corrupt file falls back to defaults instead of crashing
        with open(path, "w") as f:
            f.write("{not json")
        recovered = profile_mod.load(path=path)
        assert profile_mod.game_section(recovered, "voxelhell")["lifetime"]["runs"] == 0
    print("profile round-trip + corruption recovery OK")


def migration_v1():
    """A v1 (single-game) save file must migrate into games.voxelhell."""
    v1 = {
        "version": 1,
        "selected_skin": "gold_ace",
        "unlocked_skins": ["vanguard", "gold_ace"],
        "achievements": {"boss_slayer": {"unlocked_at": "2026-07-11T00:00:00+00:00"}},
        "lifetime": {"runs": 7, "kills": 321, "best_score": 12345},
        "settings": {"crt": False, "fps_cap": 144},
        "leaderboard": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "profile.json")
        with open(path, "w") as f:
            json.dump(v1, f)
        migrated = profile_mod.load(path=path)
        section = profile_mod.game_section(migrated, "voxelhell")
        assert section["selected_skin"] == "gold_ace"
        assert "gold_ace" in section["unlocked_skins"]
        assert "boss_slayer" in section["achievements"]
        assert section["lifetime"]["runs"] == 7
        assert section["lifetime"]["kills"] == 321
        assert migrated["settings"]["crt"] is False
        assert migrated["settings"]["fps_cap"] == 144
        assert migrated["settings"]["vsync"] is True  # new default merged in
    print("v1 -> v2 migration OK")


# --------------------------------------------------- CAB-13: replay HMAC mark
def _sample_replay_data():
    """A small, realistic replay payload (as ReplayRecorder.build() produces)
    to exercise sign/verify against."""
    rec = replay_mod.ReplayRecorder("voxelhell", "campaign", 4242, analog=False)
    for i in range(5):
        rec.on_frame(1 / 60, InputStateStub(left=(i % 2 == 0), fire=True))
    return rec.build(score=1500)


class InputStateStub:
    def __init__(self, left=False, right=False, up=False, down=False,
                 focus=False, fire=False):
        self.left, self.right = left, right
        self.up, self.down = up, down
        self.focus, self.fire = focus, fire
        self.aim_x = self.aim_y = self.strafe = self.turn = self.look_dx = 0.0


def replay_sign_verify_roundtrip():
    data = _sample_replay_data()
    key = b"a-cabinet-signing-key"
    data["sig"] = replay_mod.sign_replay(data, key)
    assert replay_mod.verify_replay(data, key), "freshly signed replay must verify"
    print("replay sign->verify round-trip OK")


def replay_tamper_detection():
    """Mutating any single recorded field (seed, one mask, one dt) after
    signing must flip verification to False."""
    key = b"a-cabinet-signing-key"

    def signed():
        d = _sample_replay_data()
        d["sig"] = replay_mod.sign_replay(d, key)
        return d

    base = signed()
    assert replay_mod.verify_replay(base, key)

    tampered_seed = dict(base)
    tampered_seed["seed"] = base["seed"] + 1
    assert not replay_mod.verify_replay(tampered_seed, key), \
        "seed mutation must invalidate signature"

    tampered_mask = dict(base)
    tampered_mask["masks"] = list(base["masks"])
    tampered_mask["masks"][0] = (tampered_mask["masks"][0] ^ 1) & 0x3F
    assert not replay_mod.verify_replay(tampered_mask, key), \
        "single mask mutation must invalidate signature"

    tampered_dt = dict(base)
    tampered_dt["dts"] = list(base["dts"])
    tampered_dt["dts"][0] = tampered_dt["dts"][0] + 0.5
    assert not replay_mod.verify_replay(tampered_dt, key), \
        "single dt mutation must invalidate signature"

    # a wrong key must also fail, even against an otherwise-untouched payload
    assert not replay_mod.verify_replay(base, b"a-different-key")

    print("replay tamper detection OK (seed/mask/dt/wrong-key all rejected)")


def replay_unsigned_legacy_loads_unverified():
    """An old replay file saved before HMAC signing existed (no "sig" field)
    must still load and play back — just flagged unverified, never refused."""
    legacy = _sample_replay_data()
    assert "sig" not in legacy
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "legacy.json")
        replay_mod._atomic_write(path, legacy)
        # pass an explicit key so this test never touches the real profile.json
        loaded = replay_mod.load(path, key=b"whatever-local-key")
    assert loaded["verified"] is False
    assert loaded["seed"] == legacy["seed"]
    assert loaded["masks"] == legacy["masks"]
    # and it still reconstructs fine via the Replay class
    rep = replay_mod.Replay(loaded)
    assert rep.frame_count == legacy["dts"].__len__()
    print("unsigned legacy replay loads with verified=False OK")


def replay_canonicalization_stable_across_key_order():
    """The canonical JSON used for the HMAC must be stable regardless of the
    dict's insertion/key order (json.dumps(..., sort_keys=True) normalizes
    this) — so signatures produced from re-ordered-but-equal payloads match."""
    data = _sample_replay_data()
    reordered = dict(reversed(list(data.items())))
    assert list(data.items()) != list(reordered.items()), \
        "test setup bug: reordering did not actually change insertion order"
    assert data == reordered  # same content, different key order

    key = b"order-shouldnt-matter"
    sig_a = replay_mod.sign_replay(data, key)
    sig_b = replay_mod.sign_replay(reordered, key)
    assert sig_a == sig_b, "signature must not depend on dict key order"

    # verifying a signed-then-reordered copy also succeeds
    signed = dict(data)
    signed["sig"] = sig_a
    signed_reordered = dict(reversed(list(signed.items())))
    assert replay_mod.verify_replay(signed_reordered, key)
    print("replay canonicalization stable across key order OK")


def profile_export_import():
    with tempfile.TemporaryDirectory() as d:
        prof_path = os.path.join(d, "profile.json")
        exp_path = os.path.join(d, "export.json")

        # build a profile with real progress, save it, export it
        p = profile_mod.load(prof_path)         # fresh defaults
        sec = profile_mod.game_section(p, "solitaire")
        sec["achievements"]["first_win"] = {"unlocked_at": "2026-01-01T00:00:00"}
        sec["lifetime"]["sol_games"] = 42
        p["settings"]["player_name"] = "ZED"
        assert profile_mod.export_profile(p, exp_path) == exp_path

        # import round-trips: same values come back (modulo backfilled defaults)
        imported = profile_mod.import_profile(exp_path)
        assert imported is not None
        isec = profile_mod.game_section(imported, "solitaire")
        assert isec["lifetime"]["sol_games"] == 42
        assert "first_win" in isec["achievements"]
        assert imported["settings"]["player_name"] == "ZED"
        assert imported["version"] == profile_mod.SCHEMA_VERSION

        # a minimal / older dict imports and backfills to the current schema
        minimal = os.path.join(d, "minimal.json")
        with open(minimal, "w") as f:
            json.dump({"version": 2, "settings": {"player_name": "OLD"}}, f)
        m = profile_mod.import_profile(minimal)
        assert m is not None
        assert m["settings"]["player_name"] == "OLD"
        assert "cabinet_man" in m and "tabletop" in m["settings"]   # backfilled

        # corrupt file -> clean failure (None), nothing implied about current
        bad = os.path.join(d, "bad.json")
        with open(bad, "w") as f:
            f.write("{ not valid json ...")
        assert profile_mod.import_profile(bad) is None
        assert profile_mod.import_profile(os.path.join(d, "nope.json")) is None

        # backup copies the current profile to a timestamped sibling
        profile_mod.save(p, prof_path)
        backup = profile_mod.backup_profile(prof_path)
        assert backup and os.path.exists(backup)
        assert profile_mod.load(backup)["settings"]["player_name"] == "ZED"
        # nothing to back up on a fresh cabinet
        assert profile_mod.backup_profile(os.path.join(d, "absent.json")) is None
    print("profile export/import OK (round-trip, backfill, corrupt->None, backup)")


def outbox_visibility():
    from meta import outbox as outbox_mod
    # pending count reads the profile's outbox list
    assert outbox_mod.pending_count({}) == 0
    assert outbox_mod.pending_count({"outbox": [{"id": "a"}, {"id": "b"}]}) == 2

    # status line: empty when nothing pending, else count + online/offline + hint
    assert outbox_mod.status_line(0, True) == ""
    line = outbox_mod.status_line(3, False)
    assert "3 scores waiting" in line and "offline" in line and "R: retry" in line
    assert "1 score " in outbox_mod.status_line(1, True)   # singular + online
    assert "online" in outbox_mod.status_line(1, True)

    # retry summary from before/after counts
    assert "Synced 3" in outbox_mod.retry_summary(3, 0, True)
    assert outbox_mod.retry_summary(3, 1, True) == "Sent 2, 1 still queued."
    assert "Offline" in outbox_mod.retry_summary(2, 2, False)      # nothing left
    assert "Retrying 2" in outbox_mod.retry_summary(2, 2, True)    # online, in flight

    # queueing itself is unchanged: an Outbox still enqueues to profile["outbox"]
    class _Net:
        available = False
    prof = {}
    ob = outbox_mod.Outbox(prof, _Net())
    ob.queue_score("voxelhell", "campaign", "AAA", 100)
    assert outbox_mod.pending_count(prof) == 1
    print("outbox visibility OK (pending count, status line, retry summary)")


def card_sfx_generation():
    from tools import gen_sound
    builders = {
        "card_flip": gen_sound.build_card_flip,
        "card_place": gen_sound.build_card_place,
        "card_shuffle": gen_sound.build_card_shuffle,
        "chip_stack": gen_sound.build_chip_stack,
    }
    rendered = {}
    for name, build in builders.items():
        s1, s2 = build(), build()
        assert s1 == s2, f"{name} not deterministic"           # fixed-seed
        assert len(s1) > 200, f"{name} too short ({len(s1)})"   # real payload
        peak = max(abs(x) for x in s1)
        assert peak > 0.05, f"{name} silent (peak {peak})"      # audible
        assert peak <= 1.0, f"{name} clips (peak {peak})"       # normalized
        rendered[name] = s1
    # the four are genuinely different effects, not the same buffer
    assert len({tuple(s) for s in rendered.values()}) == 4
    # shuffle is the busiest/longest of the set (a flurry of flips)
    assert len(rendered["card_shuffle"]) >= len(rendered["card_flip"])
    print("card SFX generation OK (deterministic, non-silent, normalized)")


def outbox_replay_upload():
    from meta import outbox as outbox_mod

    class _Net:
        available = True
        def __init__(self):
            self.uploaded = []
        def upload_replay(self, payload, tag=None):
            self.uploaded.append((payload, tag))

    # queueing a replay stores only the path, never the payload itself
    net = _Net()
    prof = {}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "last_voxelhell_campaign.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "game": "voxelhell", "seed": 1,
                      "dts": [], "masks": [], "sig": "deadbeef"}, f)

        ob = outbox_mod.Outbox(prof, net)
        ob.queue_replay("voxelhell", "campaign", "AAA", 4200, path)
        item = prof["outbox"][0]
        assert item["type"] == "replay" and "replay" not in item and \
            item["path"] == path

        # drain reads the file fresh and posts {game,mode,name,score,replay}
        payload, tag = net.uploaded[0]
        assert payload["game"] == "voxelhell" and payload["score"] == 4200
        assert payload["replay"]["sig"] == "deadbeef"
        assert tag == ("outbox", item["id"])

        # success: the item leaves the queue and the callback fires with the
        # server-assigned id
        got = {}
        ob2 = outbox_mod.Outbox(prof, net,
                                on_replay_uploaded=lambda it, rid: got.update(id=rid))
        ob2.handle_result(("outbox", item["id"]), {"id": 77})
        assert outbox_mod.pending_count(prof) == 0
        assert got == {"id": 77}

    # a missing/unreadable replay file is dropped outright (nothing to retry)
    prof2 = {}
    ob3 = outbox_mod.Outbox(prof2, net)
    ob3.queue_replay("voxelhell", "campaign", "AAA", 1, "/no/such/file.json")
    assert outbox_mod.pending_count(prof2) == 0
    print("outbox replay upload OK (path-only queueing, drain payload shape, "
          "success callback, unreadable-file drop)")


def completion_summary():
    from meta import completion as comp_mod

    class _A:
        def __init__(self, aid):
            self.id = aid

    class _Mod:
        def __init__(self, ids):
            self.ACHIEVEMENTS = [_A(i) for i in ids]

    modules = {
        "alpha": _Mod(["a1", "a2", "a3"]),
        "beta": _Mod(["b1", "b2"]),
    }
    # fabricated profile: alpha 2/3, beta 0/2, ambient 1 earned, cabinet_man 0
    profile = {
        "games": {
            "alpha": {"achievements": {"a1": {}, "a2": {}}},
            "beta": {"achievements": {}},
        },
        "ambient": {"achievements": {"night_owl": {}}},
    }
    comp = comp_mod.completion(profile, modules)
    assert comp["per_game"]["alpha"] == (2, 3), comp["per_game"]
    assert comp["per_game"]["beta"] == (0, 2), comp["per_game"]
    amb_earned, amb_total = comp["ambient"]
    assert amb_earned == 1 and amb_total == 4, comp["ambient"]
    cm_earned, cm_total = comp["cabinet_man"]
    assert cm_earned == 0 and cm_total >= 1, comp["cabinet_man"]
    earned, total = comp["total"]
    assert earned == 2 + 0 + amb_earned + cm_earned, comp["total"]
    assert total == 3 + 2 + amb_total + cm_total, comp["total"]

    # stale/unknown recorded ids never inflate earned past the module's own set
    profile2 = {"games": {"alpha": {"achievements": {"a1": {}, "zz": {}}}}}
    c2 = comp_mod.completion(profile2, {"alpha": _Mod(["a1", "a2", "a3"])})
    assert c2["per_game"]["alpha"] == (1, 3), c2["per_game"]

    # reading completion must not mutate the caller's profile (no section spawn)
    empty = {}
    comp_mod.completion(empty, modules)
    assert empty == {}, empty

    # zero-state: fresh profile -> 0/N with no ZeroDivision in the % line
    fresh = comp_mod.completion({}, modules)
    assert fresh["total"][0] == 0, fresh["total"]
    line0 = comp_mod.completion_line(fresh)
    assert "0%" in line0 and "0/" in line0, line0
    # a real summary renders "earned/total · pct%"
    line = comp_mod.completion_line(comp)
    assert "/" in line and "%" in line, line
    # fully-complete rolls up to 100%
    full = comp_mod.completion_line({"total": (5, 5)})
    assert "100%" in full, full
    print("completion summary OK (per-game + ambient + cabinet-man rollup, "
          "zero-state, no mutation)")


if __name__ == "__main__":
    migration_v1()
    p = run_campaign_with_meta()
    round_trip(p)
    replay_sign_verify_roundtrip()
    replay_tamper_detection()
    replay_unsigned_legacy_loads_unverified()
    replay_canonicalization_stable_across_key_order()
    profile_export_import()
    outbox_visibility()
    outbox_replay_upload()
    completion_summary()
    card_sfx_generation()
    print("ALL META TESTS PASSED")
