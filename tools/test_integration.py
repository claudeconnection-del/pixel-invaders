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

        # offline degradation: dead port must yield None results, no raise
        dead = ArcadeClient("http://127.0.0.1:1")
        dead.submit_score("voxelhell", "campaign", "AAA", 1)
        dead.fetch_scores("voxelhell", "campaign")
        results = drain(dead, 2, timeout_s=12)
        assert len(results) == 2 and all(p is None for _, p in results)
        print("offline degradation OK")
    finally:
        server.terminate()
        server.wait(timeout=10)
    print("ALL INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    main()
