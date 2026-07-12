"""Post-deploy smoke test, run on the box against the LIVE service after
every automated redeploy. Stdlib only — no pip installs needed on the box.

Usage: python3 server/deploy_smoke.py [base_url]   (default http://localhost:8000)

Uses game id "_ci" so test traffic lands on a board no game ever shows.
Exits non-zero (failing the deploy job) if anything is off.
"""
import json
import random
import string
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
HEALTH_TRIES = 30
HEALTH_WAIT_S = 2


def call(method, path, body=None):
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=6) as resp:
        raw = resp.read().decode()
        ctype = resp.headers.get("Content-Type", "")
        return json.loads(raw) if "json" in ctype else raw


def wait_healthy():
    for attempt in range(HEALTH_TRIES):
        try:
            if call("GET", "/healthz")["status"] == "ok":
                print(f"healthz OK (attempt {attempt + 1})")
                return
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            pass
        time.sleep(HEALTH_WAIT_S)
    sys.exit("FAIL: service never became healthy")


def main():
    print(f"deploy smoke against {BASE}")
    wait_healthy()

    tag = "".join(random.choices(string.ascii_uppercase, k=3))
    score = random.randint(1000, 999999)

    # score round trip on the hidden _ci board
    out = call("POST", "/api/v1/scores",
               {"game": "_ci", "mode": "smoke", "name": tag, "score": score})
    assert out["rank"] >= 1, out
    board = call("GET", "/api/v1/scores?game=_ci&mode=smoke&limit=100")
    assert any(s["name"] == tag and s["score"] == score
               for s in board["scores"]), "submitted score not on board"
    print(f"score round trip OK ({tag}={score})")

    # scoreboard page renders
    page = call("GET", "/scoreboard?game=_ci&mode=smoke")
    assert tag in page, "scoreboard page missing the test entry"
    print("scoreboard page OK")

    # multiplayer session round trip
    session = call("POST", "/api/v1/sessions",
                   {"game": "_ci", "mode": "smoke", "host": "CI"})
    code = session["code"]
    call("POST", f"/api/v1/sessions/{code}/join", {"name": "CI2"})
    call("POST", f"/api/v1/sessions/{code}/scores",
         {"name": "CI2", "score": 42})
    state = call("GET", f"/api/v1/sessions/{code}")
    names = {p["name"] for p in state["players"]}
    assert names == {"CI", "CI2"}, names
    assert state["players"][0]["score"] == 42
    print(f"session round trip OK (code={code})")

    # daily seed stable
    a = call("GET", "/api/v1/daily")
    b = call("GET", "/api/v1/daily")
    assert a["seed"] == b["seed"]
    print("daily seed OK")

    print("DEPLOY SMOKE PASSED")


if __name__ == "__main__":
    main()
