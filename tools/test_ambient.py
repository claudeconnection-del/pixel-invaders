"""Headless ambient-mode tests: preset round-trip, unlock gating, custom slots,
idle routing, and the mood-achievement predicates. No pygame, no GL.

Run: python tools/test_ambient.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ambient.preset import (  # noqa: E402
    AMBIENT_ACHIEVEMENTS, AmbientPreset, DEFAULTS, available_presets,
    custom_presets, idle_target)


def test_preset_roundtrip():
    p = DEFAULTS[0]
    blob = json.dumps(p.to_dict())            # must be JSON-serialisable
    back = AmbientPreset.from_dict(json.loads(blob))
    assert back.to_dict() == p.to_dict()
    assert back.id == p.id and back.palette == p.palette
    print("preset round-trip OK")


def test_unlock_gating():
    premium = [p for p in DEFAULTS if p.premium]
    assert premium, "expected some premium presets"
    prem = premium[0]
    free = available_presets(set())
    assert prem.id not in {p.id for p in free}, "premium leaked while locked"
    assert all(p.premium is None for p in free)
    unlocked = available_presets({prem.premium})
    assert prem.id in {p.id for p in unlocked}, "premium not shown after unlock"
    print(f"unlock gating OK ({len(premium)} premium, "
          f"{len(DEFAULTS) - len(premium)} free)")


def test_custom_presets():
    p = AmbientPreset("custom_x", "My Calm", "embers", [[238, 169, 76]], speed=0.7)
    loaded = custom_presets({"custom": [p.to_dict()]})
    assert len(loaded) == 1 and loaded[0].id == "custom_x" and loaded[0].speed == 0.7
    assert custom_presets({}) == []
    print("custom presets OK")


def test_idle_target():
    assert idle_target("attract") == "attract"
    assert idle_target("ambient") == "ambient"
    assert idle_target("off") is None
    assert idle_target("garbage") == "attract"   # safe default preserves behavior
    print("idle target OK")


def test_ambient_achievements():
    by_id = {a[0]: a[3] for a in AMBIENT_ACHIEVEMENTS}
    base = {"session_seconds": 0, "idle_entries": 0, "since_run_end_s": 1e9, "hour": 12}

    def ctx(**kw):
        c = dict(base); c.update(kw); return c

    assert by_id["deep_breath"](ctx(session_seconds=600))
    assert not by_id["deep_breath"](ctx(session_seconds=599))
    assert by_id["drifted_off"](ctx(idle_entries=25))
    assert not by_id["drifted_off"](ctx(idle_entries=24))
    assert by_id["take_a_break"](ctx(since_run_end_s=30))
    assert not by_id["take_a_break"](ctx(since_run_end_s=120))
    assert by_id["night_owl"](ctx(hour=2))
    assert not by_id["night_owl"](ctx(hour=12))
    print(f"ambient achievements OK ({len(AMBIENT_ACHIEVEMENTS)} rules)")


def main():
    test_preset_roundtrip()
    test_unlock_gating()
    test_custom_presets()
    test_idle_target()
    test_ambient_achievements()
    print("ALL AMBIENT TESTS PASSED")


if __name__ == "__main__":
    main()
