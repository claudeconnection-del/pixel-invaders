"""SecretLocalSession — the cabinet-side, game-agnostic coordinator for
truly-secret local multiplayer.

Threading contract (this is the whole point):
- HTTP handler threads call join() / submit() / poll() / status(). They only
  touch thread-safe structures and NEVER read or mutate the game model.
- The game thread calls pump() to apply queued actions to the authoritative
  model, then _publish() to recompute each seat's private view snapshot under
  the lock and bump its version.
- poll() returns the published snapshot (not a live projection), so a poll can
  never observe a half-applied move.

The session is game-agnostic: the game supplies callables for how a move is
applied, how a fleet is committed, when the game begins, and how a seat's
secret view is projected.
"""
import queue as _queue
import random as _random
import secrets
import threading
import time

_CODE_ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ2345679"  # no ambiguous 0/O/1/I/etc.


def _make_code(rng):
    rng = rng or _random.Random()
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(4))


def _token():
    return secrets.token_urlsafe(9)


class SecretLocalSession:
    """Coordinates two (or more) phone seats around one authoritative model.

    game hooks (all pure w.r.t. threading — only ever called on the game
    thread inside pump()):
        apply_fn(model, seat, action) -> result | None   # a play (e.g. fire)
        ready_fn(model, seat, action) -> bool             # commit a fleet
        begin_fn(model)                                   # both ready -> start
        secret_fn(model, seat) -> dict                    # this seat's view
    """

    def __init__(self, model, *, secret_fn, apply_fn, ready_fn, begin_fn,
                 seats=("P1", "P2"), code=None, rng=None):
        self.model = model
        self._secret = secret_fn
        self._apply = apply_fn
        self._ready = ready_fn
        self._begin = begin_fn
        self.seats = list(seats)
        self.code = (code or _make_code(rng)).upper()

        self._lock = threading.Lock()
        self._q = _queue.Queue()           # (seat, action) inbound from phones
        self._tokens = {}                  # seat -> token
        self._names = {}                   # seat -> display name
        self._by_name = {}                 # name -> seat
        self._ready_seats = set()
        self._seen = {}                    # seat -> last-seen monotonic time
        self._ver = {s: 0 for s in self.seats}
        self._views = {s: None for s in self.seats}   # seat -> published view

        self.gate = False                  # BoardRun sets True while animating
        self.last_error = None             # (reason, ip) for the lobby readout
        self.winner = None
        self._publish()                    # seat 0-version placeholder views

    # ================= HTTP-thread API (model-free, thread-safe) ============
    def join(self, code, name):
        name = (name or "").strip() or "P?"
        with self._lock:
            if (code or "").upper() != self.code:
                self.last_error = ("wrong_code", name)
                return {"error": "wrong_code"}
            if name in self._by_name:
                return {"error": "name_taken"}
            free = [s for s in self.seats if s not in self._tokens]
            if not free:
                self.last_error = ("full", name)
                return {"error": "full"}
            seat, token = free[0], _token()
            self._tokens[seat] = token
            self._names[seat] = name
            self._by_name[name] = seat
            self._seen[seat] = time.monotonic()
        self._publish()
        return {"seat": seat, "token": token, "code": self.code}

    def submit(self, seat, token, action):
        if not self._authed(seat, token):
            return {"error": "bad_token"}
        self._seen[seat] = time.monotonic()
        self._q.put((seat, dict(action)))
        return {"ok": True}

    def poll(self, seat, token, since):
        if not self._authed(seat, token):
            return {"error": "bad_token"}
        self._seen[seat] = time.monotonic()
        with self._lock:
            v = self._ver[seat]
            if v <= since:
                return {"v": v, "changed": False}
            return {"v": v, "view": self._views[seat]}

    def status(self):
        with self._lock:
            return {
                "code": self.code,
                "winner": self.winner,
                "seats": [
                    {"seat": s, "name": self._names.get(s),
                     "ready": s in self._ready_seats,
                     "connected": self._connected(s)}
                    for s in self.seats
                ],
                "last_error": self.last_error,
            }

    # ========================= game-thread API ==============================
    def pump(self):
        """Apply at most one queued action to the model. Gated: while `gate`
        is set (the cabinet is animating the previous move) nothing is applied.
        Returns the applied results (0 or 1) for the caller to animate."""
        if self.gate:
            return []
        try:
            seat, action = self._q.get_nowait()
        except _queue.Empty:
            return []

        kind = action.get("kind")
        results = []
        changed = False
        if kind == "ready":
            if seat not in self._ready_seats and self._ready(self.model, seat, action):
                self._ready_seats.add(seat)
                if set(self.seats) <= self._ready_seats:
                    self._begin(self.model)
                changed = True
        elif kind == "fire":
            if self.model.turn == seat:            # turn-gate on the authority
                res = self._apply(self.model, seat, action)
                if res is not None:
                    results.append(res)
                    self.winner = self.model.winner
                    changed = True
        # unknown / out-of-turn / illegal actions are simply dropped
        if changed:
            self._publish()
        return results

    def all_ready(self):
        return set(self.seats) <= self._ready_seats

    def joined_count(self):
        return len(self._tokens)

    def connected(self, seat, timeout=6.0):
        return self._connected(seat, timeout)

    # ============================== internals ===============================
    def _authed(self, seat, token):
        return self._tokens.get(seat) == token and token is not None

    def _connected(self, seat, timeout=6.0):
        t = self._seen.get(seat)
        return t is not None and (time.monotonic() - t) < timeout

    def _publish(self):
        """Recompute every seat's private view snapshot and bump its version.
        Called on the game thread (or under construction). Holds the lock so a
        concurrent poll() sees a whole, consistent view."""
        with self._lock:
            for s in self.seats:
                self._ver[s] += 1
                self._views[s] = self._secret(self.model, s)
