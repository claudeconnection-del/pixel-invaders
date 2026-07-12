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

client = TestClient(app_mod.app)


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


if __name__ == "__main__":
    test_health()
    test_submit_and_rank()
    test_validation()
    test_api_key()
    test_boards_daily_scoreboard()
    print("ALL SERVER TESTS PASSED")
