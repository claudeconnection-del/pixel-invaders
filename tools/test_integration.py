"""End-to-end integration: real uvicorn server + the game's net client.

Run with: python tools/test_integration.py
Starts the backend on a local port with a temp DB, then exercises the
stdlib client the game uses (submit, fetch, offline behavior).
"""
import os
import subprocess
import sys
import tempfile
import time
import json
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.netclient import ArcadeClient  # noqa: E402

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"


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


def main():
    env = dict(os.environ)
    env["ARCADE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "itest.db")
    env.pop("CABINET_MAN_SERVER", None)
    env.pop("PIXEL_INVADERS_SERVER", None)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_for_health(), "server never became healthy"
        print("server up")

        client = ArcadeClient(BASE)
        assert client.available

        client.submit_score("voxelhell", "campaign", "MSE", 4321, wave=6)
        results = drain(client, 1)
        assert results and results[0][0] == "submit"
        assert results[0][1] is not None and results[0][1]["rank"] == 1
        print("submit via game client OK (rank 1)")

        client.fetch_scores("voxelhell", "campaign")
        results = drain(client, 1)
        tag, payload = results[0]
        assert tag == ("scores", "voxelhell", "campaign")
        assert payload["scores"][0]["name"] == "MSE"
        assert payload["scores"][0]["score"] == 4321
        print("fetch via game client OK")

        # scoreboard page for the website embed
        with urllib.request.urlopen(
                f"{BASE}/scoreboard?game=voxelhell&mode=campaign") as r:
            page = r.read().decode()
        assert "MSE" in page and "VOXEL HELL" in page
        print("scoreboard embed page OK")

        # multiplayer sessions through the game client: host + join, same
        # seed, both submit, lobby board sorts
        host = ArcadeClient(BASE)
        host.create_session("voxelhell", "campaign", "MSE")
        (tag, payload), = drain(host, 1)
        assert tag == "session_create" and payload is not None
        code, seed = payload["code"], payload["seed"]

        friend = ArcadeClient(BASE)
        friend.join_session(code, "BUN")
        (tag, payload), = drain(friend, 1)
        assert tag == "session_join" and payload["seed"] == seed
        assert {p["name"] for p in payload["players"]} == {"MSE", "BUN"}

        # both players race the same seeded world — identical waves
        import random
        from games.voxelhell.world import World
        from games.voxelhell.bot import demo_bot
        scores = {}
        for name in ("MSE", "BUN"):
            w = World(rng=random.Random(seed), mode="campaign")
            for _ in range(60 * 30):
                w.update(1 / 60, demo_bot(w))
                w.drain_events()
                if w.run_over:
                    break
            scores[name] = w.score
        assert scores["MSE"] == scores["BUN"], "same seed must be a fair race"

        host.submit_session_score(code, "MSE", scores["MSE"] + 500, wave=6)
        friend.submit_session_score(code, "BUN", scores["BUN"], wave=5)
        drain(host, 1)
        drain(friend, 1)
        host.get_session(code)
        (tag, payload), = drain(host, 1)
        players = payload["players"]
        assert players[0]["name"] == "MSE" and players[1]["name"] == "BUN"
        assert players[0]["score"] == scores["MSE"] + 500
        print(f"multiplayer session OK (code={code}, fair seed verified)")

        # offline degradation: dead port must yield None results, no raise
        dead = ArcadeClient("http://127.0.0.1:1")
        dead.submit_score("voxelhell", "campaign", "AAA", 1)
        dead.fetch_scores("voxelhell", "campaign")
        results = drain(dead, 2, timeout_s=12)
        assert len(results) == 2 and all(p is None for _, p in results)
        print("offline degradation OK")

        # outbox: scores queued while offline deliver on next contact;
        # definitively-rejected items (bad session) get dropped
        from meta.outbox import Outbox
        profile = {"outbox": []}
        ranks = []
        offline_net = ArcadeClient("http://127.0.0.1:1")
        box = Outbox(profile, offline_net, on_rank=ranks.append)
        box.queue_score("voxelhell", "campaign", "OFF", 9999, wave=4)
        box.queue_session_score("ZZZZ", "OFF", 123)  # will 404 once online
        for tag, payload in drain(offline_net, 2, timeout_s=12):
            box.handle_result(tag, payload)
        assert len(profile["outbox"]) == 2, "offline items must stay queued"

        box.net = ArcadeClient(BASE)  # back on the home network
        box.inflight.clear()
        box.drain()
        for tag, payload in drain(box.net, 2):
            box.handle_result(tag, payload)
        assert profile["outbox"] == [], f"outbox not drained: {profile['outbox']}"
        assert ranks and ranks[0] >= 1, "rank toast never fired"
        with urllib.request.urlopen(
                f"{BASE}/api/v1/scores?game=voxelhell&mode=campaign") as r:
            names = [s["name"] for s in json.loads(r.read())["scores"]]
        assert "OFF" in names, "queued score never reached the board"
        print("offline outbox OK (deferred delivery + 4xx drop)")
    finally:
        server.terminate()
        server.wait(timeout=10)
    print("ALL INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    main()
