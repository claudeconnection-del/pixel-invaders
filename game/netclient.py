"""Optional arcade-backend client. Stdlib only (urllib), every call runs on
a worker thread and never blocks a frame; failures degrade silently to
offline. Results are collected via poll() on the main thread.

Server URL comes from settings.server_url or the PIXEL_INVADERS_SERVER env
var (env wins). Empty = offline mode.
"""
import json
import os
import queue
import threading
import urllib.error
import urllib.request

TIMEOUT_S = 4


class ArcadeClient:
    def __init__(self, base_url="", api_key=""):
        env = os.environ.get("PIXEL_INVADERS_SERVER", "")
        self.base_url = (env or base_url or "").rstrip("/")
        self.api_key = api_key or os.environ.get("PIXEL_INVADERS_API_KEY", "")
        self.results = queue.Queue()

    @property
    def available(self):
        return bool(self.base_url)

    # ------------------------------------------------------------ plumbing
    def _request(self, tag, method, path, body=None):
        def work():
            url = f"{self.base_url}{path}"
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("X-Api-Key", self.api_key)
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    payload = json.loads(resp.read().decode())
                self.results.put((tag, payload))
            except (urllib.error.URLError, OSError, ValueError):
                self.results.put((tag, None))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        """Drain finished results: list of (tag, payload-or-None)."""
        out = []
        while True:
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                return out

    # ------------------------------------------------------------- calls
    def submit_score(self, game, mode, name, score, wave=None):
        if not self.available:
            return
        self._request("submit", "POST", "/api/v1/scores", {
            "game": game, "mode": mode, "name": name,
            "score": score, "wave": wave,
        })

    def fetch_scores(self, game, mode, limit=10):
        if not self.available:
            return
        self._request(("scores", game, mode), "GET",
                      f"/api/v1/scores?game={game}&mode={mode}&limit={limit}")

    # ------------------------------------------------- multiplayer sessions
    def create_session(self, game, mode, host):
        if not self.available:
            return
        self._request("session_create", "POST", "/api/v1/sessions",
                      {"game": game, "mode": mode, "host": host})

    def join_session(self, code, name):
        if not self.available:
            return
        self._request("session_join", "POST",
                      f"/api/v1/sessions/{code}/join", {"name": name})

    def submit_session_score(self, code, name, score, wave=None):
        if not self.available:
            return
        self._request("session_score", "POST",
                      f"/api/v1/sessions/{code}/scores",
                      {"name": name, "score": score, "wave": wave})

    def get_session(self, code):
        if not self.available:
            return
        self._request("session_state", "GET", f"/api/v1/sessions/{code}")
