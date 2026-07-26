"""End-to-end integration: real uvicorn server + the game's net client, the
replay upload/list/fetch flow (CAB-15). Mirrors tools/test_integration.py's
subprocess+drain() pattern, on its own port so it never disturbs that file's
key-less server.

Run with: python tools/test_replay_integration.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.netclient import ArcadeClient  # noqa: E402
from meta.outbox import Outbox  # noqa: E402
from meta.replay import sign_replay  # noqa: E402

PORT = 8792
BASE = f"http://127.0.0.1:{PORT}"
API_KEY = "sekrit-replay-key"


def wait_for_health(timeout_s=15):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.3)
    return False


def drain(client, want, timeout_s=8):
    deadline = time.time() + timeout_s
    got = []
    while time.time() < deadline and len(got) < want:
        got += client.poll()
        time.sleep(0.05)
    return got


def _replay(score, seed=99, game="voxelhell", mode="campaign", frames=3):
    data = {"schema": 1, "game": game, "mode": mode, "seed": seed,
            "analog": False, "score": score, "created": "2026-07-26T00:00:00",
            "duration": round(0.016 * frames, 2),
            "dts": [0.016] * frames, "masks": [0] * frames, "analog_data": []}
    data["sig"] = sign_replay(data, API_KEY)
    return data


def main():
    env = dict(os.environ)
    env["ARCADE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "replay_itest.db")
    env["ARCADE_API_KEY"] = API_KEY
    env.pop("CABINET_MAN_SERVER", None)
    env.pop("PIXEL_INVADERS_SERVER", None)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_for_health(), "server never became healthy"
        print("server up")

        client = ArcadeClient(BASE, api_key=API_KEY)
        assert client.available

        # submit the score first: CAB-14's upload gate requires a qualifying
        # (top-10) score already on the board
        client.submit_score("voxelhell", "campaign", "REP", 5000)
        (tag, payload), = drain(client, 1)
        assert tag == "submit" and payload["rank"] == 1

        replay = _replay(5000)
        client.upload_replay({"game": "voxelhell", "mode": "campaign",
                              "name": "REP", "score": 5000, "replay": replay},
                             tag="replay_up")
        (tag, payload), = drain(client, 1)
        assert tag == "replay_up" and "id" in payload, payload
        replay_id = payload["id"]
        print("upload via game client OK")

        client.fetch_replays("voxelhell", "campaign")
        (tag, payload), = drain(client, 1)
        assert tag == ("replays", "voxelhell", "campaign")
        assert any(e["id"] == replay_id and e["name"] == "REP"
                  for e in payload["replays"])
        print("list via game client OK")

        client.fetch_replay(replay_id, tag=("replay_fetch", replay_id))
        (tag, payload), = drain(client, 1)
        assert tag == ("replay_fetch", replay_id)
        assert payload["seed"] == 99 and payload["score"] == 5000
        assert payload["sig"] == replay["sig"]
        print("fetch via game client OK")

        # a replay for a score that never qualified (never submitted / not
        # top-10) is rejected server-side; the outbox drops it — nothing to
        # retry, since it will never become eligible on its own
        orphan_replay = _replay(1, seed=1)
        profile = {"outbox": []}
        box = Outbox(profile, ArcadeClient(BASE, api_key=API_KEY))
        d = tempfile.mkdtemp()
        path = os.path.join(d, "orphan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(orphan_replay, f)
        box.queue_replay("voxelhell", "campaign", "ORF", 1, path)
        for tag, payload in drain(box.net, 1, timeout_s=12):
            box.handle_result(tag, payload)
        assert profile["outbox"] == [], "unqualified replay must not linger"
        print("orphan replay rejected + dropped OK (CAB-14 gate)")

        # an unreachable server: upload/fetch degrade to None, never raise
        dead = ArcadeClient("http://127.0.0.1:1")
        dead.upload_replay({"game": "voxelhell", "mode": "campaign",
                            "name": "X", "score": 1, "replay": _replay(1)})
        dead.fetch_replays("voxelhell", "campaign")
        results = drain(dead, 2, timeout_s=12)
        assert len(results) == 2 and all(p is None for _, p in results)
        print("offline replay degradation OK")
    finally:
        server.terminate()
        server.wait(timeout=10)
    print("ALL REPLAY INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    main()
