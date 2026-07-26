"""Backend API tests (FastAPI TestClient; needs httpx as a dev dependency).

Run with: python server/test_server.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["ARCADE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ARCADE_API_KEY"] = ""  # exercise both modes below

from fastapi.testclient import TestClient  # noqa: E402

import server.app as app_mod  # noqa: E402
from server import db  # noqa: E402
from meta.replay import sign_replay  # noqa: E402

client = TestClient(app_mod.app)


def _make_replay(key, score=1234, seed=42, game="voxelhell", mode="campaign",
                 frames=2):
    data = {
        "schema": 1, "game": game, "mode": mode, "seed": seed,
        "analog": False, "score": score, "created": "2026-07-25T00:00:00",
        "duration": round(0.016 * frames, 2),
        "dts": [0.016] * frames, "masks": [0] * frames, "analog_data": [],
    }
    data["sig"] = sign_replay(data, key)
    return data


def test_health():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    print("healthz OK")


def test_submit_and_rank():
    db.reset_for_tests()
    r = client.post("/api/v1/scores", json={
        "game": "voxelhell", "mode": "campaign", "name": "abc",
        "score": 1000, "wave": 6})
    assert r.status_code == 200 and r.json()["rank"] == 1
    r = client.post("/api/v1/scores", json={
        "game": "voxelhell", "mode": "campaign", "name": "ZZZ", "score": 2000})
    assert r.json()["rank"] == 1
    r = client.post("/api/v1/scores", json={
        "game": "voxelhell", "mode": "campaign", "name": "MID", "score": 1500})
    assert r.json()["rank"] == 2

    r = client.get("/api/v1/scores",
                   params={"game": "voxelhell", "mode": "campaign"})
    scores = r.json()["scores"]
    assert [s["name"] for s in scores] == ["ZZZ", "MID", "ABC"]
    assert scores[0]["rank"] == 1 and scores[2]["wave"] == 6
    print("submit + rank OK")


def test_validation():
    bad = [
        {"game": "no slugs!", "mode": "campaign", "name": "AAA", "score": 1},
        {"game": "voxelhell", "mode": "campaign", "name": "toolong", "score": 1},
        {"game": "voxelhell", "mode": "campaign", "name": "a!", "score": 1},
        {"game": "voxelhell", "mode": "campaign", "name": "AAA", "score": -5},
        {"game": "voxelhell", "mode": "campaign", "name": "AAA",
         "score": 10**12},
    ]
    for body in bad:
        r = client.post("/api/v1/scores", json=body)
        assert r.status_code == 422, f"{body} -> {r.status_code}"
    print("validation OK")


def test_api_key():
    app_mod.API_KEY = "sekrit"
    try:
        r = client.post("/api/v1/scores", json={
            "game": "voxelhell", "mode": "campaign", "name": "KEY", "score": 5})
        assert r.status_code == 401
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "campaign",
                              "name": "KEY", "score": 5})
        assert r.status_code == 200
    finally:
        app_mod.API_KEY = ""
    print("api key OK")


def test_boards_daily_scoreboard():
    r = client.get("/api/v1/boards")
    assert {"game": "voxelhell", "mode": "campaign"} in r.json()["boards"]
    r = client.get("/api/v1/daily")
    body = r.json()
    assert isinstance(body["seed"], int) and body["date"]
    again = client.get("/api/v1/daily").json()
    assert again["seed"] == body["seed"], "daily seed must be stable"
    r = client.get("/scoreboard",
                   params={"game": "voxelhell", "mode": "campaign"})
    assert r.status_code == 200
    assert "VOXEL HELL" in r.text and "ZZZ" in r.text
    print("boards + daily + scoreboard OK")


def test_sessions():
    db.reset_for_tests()
    # host a session
    r = client.post("/api/v1/sessions", json={
        "game": "voxelhell", "mode": "campaign", "host": "moose"})
    assert r.status_code == 200
    body = r.json()
    code, seed = body["code"], body["seed"]
    assert len(code) == 4 and isinstance(seed, int)

    # join: ok, duplicate name rejected, bad code 404
    r = client.post(f"/api/v1/sessions/{code}/join", json={"name": "bun"})
    assert r.status_code == 200
    assert {p["name"] for p in r.json()["players"]} == {"MOOSE", "BUN"}
    assert r.json()["seed"] == seed
    r = client.post(f"/api/v1/sessions/{code}/join", json={"name": "bun"})
    assert r.status_code == 409
    r = client.post("/api/v1/sessions/ZZZZ/join", json={"name": "who"})
    assert r.status_code == 404

    # scores: best kept, outsiders rejected, board sorted
    for name, score in (("moose", 5000), ("bun", 7000), ("moose", 4000)):
        r = client.post(f"/api/v1/sessions/{code}/scores",
                        json={"name": name, "score": score, "wave": 3})
        assert r.status_code == 200
    r = client.post(f"/api/v1/sessions/{code}/scores",
                    json={"name": "intruder", "score": 1})
    assert r.status_code == 404
    session = client.get(f"/api/v1/sessions/{code}").json()
    players = session["players"]
    assert players[0]["name"] == "BUN" and players[0]["score"] == 7000
    assert players[1]["name"] == "MOOSE" and players[1]["score"] == 5000
    print("sessions OK (host/join/score/sort/validation)")


def test_matches():
    db.reset_for_tests()
    # host a match with an opaque board state, MOOSE to move first
    r = client.post("/api/v1/matches", json={
        "game": "battleship", "host": "moose",
        "state": {"phase": "play", "boards": {}}, "turn": "moose"})
    assert r.status_code == 200, r.text
    m = r.json()
    code, v = m["code"], m["version"]
    assert len(code) == 4 and v == 1 and m["turn"] == "MOOSE"

    # opponent joins
    r = client.post(f"/api/v1/matches/{code}/join", json={"name": "bun"})
    assert r.status_code == 200
    assert {p for p in r.json()["players"]} == {"MOOSE", "BUN"}

    # BUN can't move — not their turn
    r = client.post(f"/api/v1/matches/{code}/move", json={
        "name": "bun", "base_version": 1, "state": {"x": 1}, "turn": "BUN"})
    assert r.status_code == 403

    # MOOSE moves, handing the turn to BUN; version bumps
    r = client.post(f"/api/v1/matches/{code}/move", json={
        "name": "moose", "base_version": 1,
        "state": {"phase": "play", "shot": [3, 4]}, "turn": "BUN"})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["turn"] == "BUN" and r.json()["state"]["shot"] == [3, 4]

    # MOOSE tries again at the stale version -> not their turn now (403)
    r = client.post(f"/api/v1/matches/{code}/move", json={
        "name": "moose", "base_version": 2, "state": {}, "turn": "MOOSE"})
    assert r.status_code == 403

    # version-conflict: BUN submits an outdated base_version
    r = client.post(f"/api/v1/matches/{code}/move", json={
        "name": "bun", "base_version": 1, "state": {}, "turn": "MOOSE"})
    assert r.status_code == 409

    # poll with since=1 sees the change; since=2 does not
    r = client.get(f"/api/v1/matches/{code}", params={"since": 1})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["state"]["shot"] == [3, 4]
    r = client.get(f"/api/v1/matches/{code}", params={"since": 2})
    assert r.json()["changed"] is False

    # unknown code + oversized state rejected
    assert client.get("/api/v1/matches/ZZZZ").status_code == 404
    big = {"blob": "x" * 70000}
    r = client.post("/api/v1/matches", json={
        "game": "battleship", "host": "moose", "state": big})
    assert r.status_code == 413
    print("matches OK (create/join/turn-gate/version-conflict/poll/limits)")


def test_replay_upload_list_fetch_roundtrip():
    db.reset_for_tests()
    app_mod.API_KEY = "sekrit"
    try:
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "campaign",
                              "name": "ABC", "score": 1234})
        assert r.status_code == 200, r.text

        replay = _make_replay("sekrit", score=1234)
        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "ABC",
            "score": 1234, "replay": replay})
        assert r.status_code == 200, r.text
        replay_id = r.json()["id"]

        r = client.get("/replays",
                       params={"game": "voxelhell", "mode": "campaign"})
        assert r.status_code == 200
        entries = r.json()["replays"]
        assert any(e["id"] == replay_id and e["name"] == "ABC"
                   and e["score"] == 1234 for e in entries), entries

        r = client.get(f"/replays/{replay_id}")
        assert r.status_code == 200, r.text
        fetched = r.json()
        assert fetched["seed"] == 42 and fetched["score"] == 1234
        assert fetched["sig"] == replay["sig"]

        # never-submitted score: no matching entry to attach to
        orphan = _make_replay("sekrit", score=999999)
        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "ABC",
            "score": 999999, "replay": orphan})
        assert r.status_code == 409, r.status_code
    finally:
        app_mod.API_KEY = ""
    print("replay upload/list/fetch round-trip OK")


def test_replay_bad_signature_rejected():
    db.reset_for_tests()
    app_mod.API_KEY = "sekrit"
    try:
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "campaign",
                              "name": "BAD", "score": 999})
        assert r.status_code == 200

        replay = _make_replay("wrong-key", score=999)
        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "BAD",
            "score": 999, "replay": replay})
        assert 400 <= r.status_code < 500, r.status_code

        tampered = _make_replay("sekrit", score=999)
        tampered["score"] = 999000  # mutate after signing -> sig mismatch
        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "BAD",
            "score": 999, "replay": tampered})
        assert 400 <= r.status_code < 500, r.status_code
    finally:
        app_mod.API_KEY = ""
    print("bad signature rejected OK")


def test_replay_oversize_rejected():
    db.reset_for_tests()
    app_mod.API_KEY = "sekrit"
    try:
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "campaign",
                              "name": "BIG", "score": 42})
        assert r.status_code == 200

        replay = _make_replay("sekrit", score=42, frames=60000)
        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "BIG",
            "score": 42, "replay": replay})
        assert r.status_code == 413, r.status_code
    finally:
        app_mod.API_KEY = ""
    print("oversize replay rejected OK")


def test_replay_retention_prunes_dropped_score():
    db.reset_for_tests()
    app_mod.API_KEY = "sekrit"
    try:
        ids = {}
        for i in range(10):
            score = 100 + i
            name = f"P{i}"
            r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                            json={"game": "voxelhell", "mode": "retention",
                                  "name": name, "score": score})
            assert r.status_code == 200, r.text
        for i in range(10):
            score = 100 + i
            name = f"P{i}"
            replay = _make_replay("sekrit", score=score, game="voxelhell",
                                  mode="retention")
            r = client.post("/replays", headers={"X-Api-Key": "sekrit"},
                            json={"game": "voxelhell", "mode": "retention",
                                  "name": name, "score": score,
                                  "replay": replay})
            assert r.status_code == 200, r.text
            ids[score] = r.json()["id"]

        before = client.get("/replays", params={
            "game": "voxelhell", "mode": "retention"}).json()["replays"]
        assert len(before) == 10

        # a big new score bumps the lowest (100) off the top 10
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "retention",
                              "name": "TOP", "score": 5000})
        assert r.status_code == 200

        after = client.get("/replays", params={
            "game": "voxelhell", "mode": "retention"}).json()["replays"]
        after_ids = {e["id"] for e in after}
        assert ids[100] not in after_ids, "dropped score's replay must be pruned"
        assert len(after) == 9
        for score in range(101, 110):
            assert ids[score] in after_ids
    finally:
        app_mod.API_KEY = ""
    print("retention prunes dropped-score replay OK")


def test_replay_api_key_required():
    db.reset_for_tests()
    app_mod.API_KEY = "sekrit"
    try:
        r = client.post("/api/v1/scores", headers={"X-Api-Key": "sekrit"},
                        json={"game": "voxelhell", "mode": "campaign",
                              "name": "KEY", "score": 77})
        assert r.status_code == 200

        replay = _make_replay("sekrit", score=77)
        r = client.post("/replays", json={
            "game": "voxelhell", "mode": "campaign", "name": "KEY",
            "score": 77, "replay": replay})
        assert r.status_code == 401, r.status_code

        r = client.post("/replays", headers={"X-Api-Key": "sekrit"}, json={
            "game": "voxelhell", "mode": "campaign", "name": "KEY",
            "score": 77, "replay": replay})
        assert r.status_code == 200, r.text
    finally:
        app_mod.API_KEY = ""
    print("replay upload requires api key OK")


def test_score_submit_path_unaffected_by_replays():
    db.reset_for_tests()
    r = client.post("/api/v1/scores", json={
        "game": "voxelhell", "mode": "campaign", "name": "OLD", "score": 42})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"id", "rank"}, body
    assert body["rank"] == 1
    r = client.get("/api/v1/scores",
                   params={"game": "voxelhell", "mode": "campaign"})
    assert r.status_code == 200
    assert any(s["name"] == "OLD" for s in r.json()["scores"])
    print("old score-submit path unaffected OK")


if __name__ == "__main__":
    test_health()
    test_submit_and_rank()
    test_validation()
    test_api_key()
    test_boards_daily_scoreboard()
    test_sessions()
    test_matches()
    test_replay_upload_list_fetch_roundtrip()
    test_replay_bad_signature_rejected()
    test_replay_oversize_rejected()
    test_replay_retention_prunes_dropped_score()
    test_replay_api_key_required()
    test_score_submit_path_unaffected_by_replays()
    print("ALL SERVER TESTS PASSED")
