# Secret Local Multiplayer (Companion Phones) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. This plan is being implemented inline in the authoring session.

**Goal:** Make Battleship playable by two people in one room with their hidden state (ship placement) genuinely un-seeable by the opponent — each player's phone is a private controller, the cabinet is the shared TV — on a reusable `games/board/` seam.

**Architecture:** The cabinet keeps the authoritative `BattleshipModel` on its game thread and runs a stdlib HTTP long-poll server on a daemon thread. Phones (one self-contained HTML file, served by the cabinet) join over the LAN, place fleets, and fire; the cabinet applies moves, animates them on the public board, and pushes each seat only its own `secret_view`. Two pure projection functions per game (`public_view`, `secret_view`) are the secrecy boundary and the generalisable seam.

**Tech Stack:** Python 3.14 (stdlib `http.server`/`socketserver`/`queue`/`threading` only — no new runtime deps for transport), pygame + PyOpenGL (existing engine), `segno` (pure-Python QR, new dep, dev/optional), vanilla HTML/CSS/JS phone client.

## Global Constraints

- Python 3.14; **stdlib-only** for the companion transport (matches `game/netclient.py`'s stance).
- The authoritative model is mutated **only on the game thread**; HTTP handler threads only enqueue actions and read a published snapshot. No locks on the model.
- Secrets never render on the cabinet and never leave the cabinet (self-hosted). Per-seat token gates private views. Anti-cheat is a **non-goal**.
- Reuse existing modules: `games/battleship/model.py` (unchanged), `games/board/anim.py`, `game/theme.py`, `render/renderer.py` `Batcher`/`draw_scene`, `render/text.py` `OverlayRenderer` (`.text`/`.rect`/`.image`), `arcade.game_api.GameInfo/GameRun`.
- Game module contract: `INFO`, `create_run(mode, rng)`, `ACHIEVEMENTS`. `GameRun`: `update(dt,inp)`, `draw(renderer,section)`, `draw_hud(o,w,h,section)`, `on_event(...)`, `drain_events()`, `run_stats()`, `run_summary()`, attrs `score`,`run_over`; optional `handle_key(key)->bool`, `attach_profile(section,settings,save_cb)`.
- Default host port **1983**, auto-fallback to next free / OS-assigned, manual override; real port baked into the QR.
- Headless tests run with the repo's venv: `.venv/Scripts/python.exe tools/<test>.py`. Commit after each green task.

## File structure

- Create `games/board/companion/__init__.py` — exports the seam.
- Create `games/board/companion/views.py` — `public_view`/`secret_view` protocol + shared helpers; battleship projections live in `games/battleship/game.py` (game owns its rules→view mapping).
- Create `games/board/companion/session.py` — `SecretLocalSession`: seats, tokens, action queue, per-seat versioning, liveness, `pump()`.
- Create `games/board/companion/server.py` — threaded stdlib HTTP + long-poll; serves the phone app; `pick_port()`.
- Create `games/board/companion/qr.py` — QR matrix via `segno` (fallback: text-only if unavailable).
- Create `games/board/phone/app.html` — host-agnostic phone client.
- Create `games/board/run.py` — `BoardRun` base (model ↔ session ↔ anim ↔ public renderer; `SECRET_LOCAL` mode).
- Create `games/battleship/game.py` — `INFO`, `BattleshipRun(BoardRun)`, `create_run`, public renderer, `public_view`/`secret_view`.
- Create `games/battleship/__init__.py`, `games/battleship/achievements.py`.
- Create `games/board/replay.py` — board-move replay: record seed+placements+moves; perspective playback.
- Modify `games/__init__.py` — add `("BOARD", ["battleship"])` category.
- Modify `game/theme.py` — battleship naval signature.
- Modify `main.py` — mode-select already handles `INFO.modes`; add the secret-local lobby/QR overlay + waiting/failure states + drive `BoardRun`; perspective picker in the replay browser.
- Modify `requirements.txt` — add `segno`.
- Tests: `tools/test_companion.py` (secrecy invariant + session + loopback server), extend `tools/test_battleship.py`.

---

## Increment 1 — projection seam + the secrecy invariant (headless)

### Task 1: `public_view` / `secret_view` for Battleship + the secrecy-invariant test

**Files:**
- Create: `games/board/companion/views.py` (protocol doc + `assert_secret` test helper)
- Create: `games/board/companion/__init__.py`
- Modify: `games/battleship/game.py` (projection functions — first code to land in this file)
- Test: `tools/test_companion.py`

**Interfaces:**
- Produces: `public_view(model) -> dict`, `secret_view(model, seat) -> dict` (in `games/battleship/game.py`); `views.exposed_enemy_cells(view_board) -> set[tuple]` helper in `games/board/companion/views.py`.

- [ ] **Step 1: Write the failing test** (`tools/test_companion.py`)

```python
"""Headless companion tests: the secrecy invariant, the session state machine,
and a loopback server round-trip. No pygame, no GL."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from games.battleship.model import BattleshipModel, PLAYERS, OTHER  # noqa: E402
from games.battleship.ai import ai_fire  # noqa: E402
from games.battleship import game as bs  # noqa: E402


def _played_game(seed):
    m = BattleshipModel(random.Random(seed))
    m.random_place("P1"); m.random_place("P2"); m.begin_fire("P1")
    for _ in range(60):
        if m.winner is not None:
            break
        x, y = ai_fire(m); m.fire(m.turn, x, y)
    return m

def _unhit_unsunk_cells(model, player):
    out = set()
    for s in model.ships[player]:
        if model.is_sunk(player, s):
            continue
        for x, y in s["cells"]:
            if not model.already_shot(player, x, y):
                out.add((x, y))
    return out

def test_secrecy_invariant():
    for seed in range(6):
        m = _played_game(seed)
        pub = bs.public_view(m)
        # public view: no un-hit un-sunk ship cell for EITHER player
        for p in PLAYERS:
            exposed = _cells_about(pub["boards"][p])
            assert exposed.isdisjoint(_unhit_unsunk_cells(m, p)), f"public leaks {p}"
        # each seat's secret view: reveals nothing new about the OPPONENT
        for seat in PLAYERS:
            sv = bs.secret_view(m, seat)
            other = OTHER[seat]
            exposed = _cells_about(sv["boards"][other])
            assert exposed.isdisjoint(_unhit_unsunk_cells(m, other)), \
                f"{seat} can see {other}'s hidden ships"
    print("secrecy invariant OK")

def _cells_about(board):
    cells = {(mk["x"], mk["y"]) for mk in board["shots"]}
    for s in board["sunk"]:
        cells |= {tuple(c) for c in s["cells"]}
    return cells

def main():
    test_secrecy_invariant()
    print("ALL COMPANION TESTS PASSED")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, watch it fail** — `.venv/Scripts/python.exe tools/test_companion.py` → `ModuleNotFoundError`/`AttributeError` (no `public_view`).

- [ ] **Step 3: Implement the projections** in `games/battleship/game.py` (module top, before the run class):

```python
from games.battleship.model import BattleshipModel, FLEET, PLAYERS, OTHER

def _shot_markers(model, target):
    """Public record of shots that have landed on `target`: hit/miss per fired
    cell. Reveals only fired cells — never an un-fired ship location."""
    out = []
    for c in model.shots[target]:
        x, y = c[0], c[1]
        out.append({"x": x, "y": y, "hit": model.ship_at(target, x, y) is not None})
    return out

def _sunk(model, player):
    return [{"name": s["name"], "cells": [list(c) for c in s["cells"]]}
            for s in model.ships[player] if model.is_sunk(player, s)]

def public_view(model):
    """Everything the shared cabinet screen may draw. No un-hit ship, ever."""
    return {
        "size": model.size, "phase": model.phase, "turn": model.turn,
        "winner": model.winner,
        "boards": {p: {"shots": _shot_markers(model, p), "sunk": _sunk(model, p),
                       "afloat": model.remaining_ships(p)} for p in PLAYERS},
    }

def secret_view(model, seat):
    """What ONE seat's phone may see: the public board + ONLY its own fleet."""
    view = public_view(model)
    view["you"] = seat
    view["your_turn"] = (model.phase == "fire" and model.turn == seat
                         and model.winner is None)
    view["your_fleet"] = [
        {"name": s["name"], "cells": [list(c) for c in s["cells"]],
         "hits": [[x, y] for x, y in s["cells"] if model.already_shot(seat, x, y)],
         "sunk": model.is_sunk(seat, s)}
        for s in model.ships[seat]]
    return view
```

- [ ] **Step 4: Run the test, watch it pass** — `.venv/Scripts/python.exe tools/test_companion.py` → `secrecy invariant OK`.

- [ ] **Step 5: Commit** — `git add games/board/companion/__init__.py games/battleship/game.py tools/test_companion.py && git commit -m "feat(board): battleship view projections + secrecy-invariant test"`

---

## Increment 2 — `SecretLocalSession` (headless state machine)

### Task 2: seats, tokens, action queue, versioning, `pump`

**Files:**
- Create: `games/board/companion/session.py`
- Test: extend `tools/test_companion.py`

**Interfaces:**
- Consumes: `public_view`/`secret_view` (passed in as callables so the session is game-agnostic), a game `model`, and an `apply(model, seat, action) -> result|None` callable (game-supplied move applier), a `ready(model, seat, payload)` callable, a `both_ready_begins(model)` callable.
- Produces:
  - `SecretLocalSession(model, *, secret_fn, apply_fn, ready_fn, begin_fn, seats=("P1","P2"), code=None, rng=None)`
  - `.join(code, name) -> {"seat","token"} | {"error": <reason>}` (reasons: `wrong_code|seat_taken|name_taken|full`)
  - `.submit(seat, token, action) -> {"ok":True} | {"error": <reason>}` (enqueue only; `not_your_turn` deferred to pump)
  - `.poll(seat, token, since) -> {"v":int,"view":dict} | {"v":int,"changed":False} | {"error":...}`
  - `.pump() -> list[result]` (GAME THREAD: apply at most one queued action if not gated; bump versions; returns applied results for animation)
  - `.touch(seat)` liveness; `.status()` for the lobby (seats, ready, connected, last_error)
  - attrs: `.code`, `.gate` (settable bool — BoardRun sets True while animating), `.winner`

- [ ] **Step 1: Write failing tests** (append to `tools/test_companion.py`) — join rules, turn-gating, version bumps, a full driven game:

```python
from games.board.companion.session import SecretLocalSession  # noqa: E402

def _bs_session(seed=1):
    m = BattleshipModel(random.Random(seed))
    def apply_fn(model, seat, a):
        if a["kind"] == "fire":
            return model.fire(seat, a["x"], a["y"])
        return None
    def ready_fn(model, seat, a):
        model.random_place(seat)  # tests use auto-place
        return True
    def begin_fn(model):
        model.begin_fire("P1")
    return SecretLocalSession(m, secret_fn=bs.secret_view, apply_fn=apply_fn,
                              ready_fn=ready_fn, begin_fn=begin_fn, code="WAVE")

def test_join_rules():
    s = _bs_session()
    assert s.join("NOPE", "Ann")["error"] == "wrong_code"
    a = s.join("WAVE", "Ann"); assert a["seat"] == "P1" and "token" in a
    assert s.join("WAVE", "Ann")["error"] == "name_taken"
    b = s.join("WAVE", "Bo"); assert b["seat"] == "P2"
    assert s.join("WAVE", "Cy")["error"] == "full"
    print("join rules OK")

def test_turn_gate_and_versions():
    s = _bs_session()
    a = s.join("WAVE", "Ann"); b = s.join("WAVE", "Bo")
    s.submit("P1", a["token"], {"kind": "ready"})
    s.submit("P2", b["token"], {"kind": "ready"}); s.pump(); s.pump()
    assert s.model.phase == "fire"
    v0 = s.poll("P1", a["token"], -1)["v"]
    # P2 firing out of turn: enqueued then rejected at pump (no state change)
    s.submit("P2", b["token"], {"kind": "fire", "x": 0, "y": 0}); s.pump()
    assert s.model.turn == "P1"
    s.submit("P1", a["token"], {"kind": "fire", "x": 0, "y": 0}); s.pump()
    assert s.model.turn == "P2"
    assert s.poll("P1", a["token"], v0)["v"] > v0  # P1's view advanced
    print("turn gate + versions OK")

# (register both in main())
```

- [ ] **Step 2: Run, watch fail** (`ImportError`).

- [ ] **Step 3: Implement `session.py`** — full code:

```python
"""SecretLocalSession — the cabinet-side, game-agnostic coordinator for
truly-secret local multiplayer. HTTP threads call join/submit/poll (they only
touch thread-safe structures); the game thread calls pump() to apply queued
actions to the authoritative model. Per-seat view versions drive long-poll."""
import queue as _queue
import secrets
import threading
import time

def _tok():
    return secrets.token_urlsafe(9)

class SecretLocalSession:
    def __init__(self, model, *, secret_fn, apply_fn, ready_fn, begin_fn,
                 seats=("P1", "P2"), code=None, rng=None):
        self.model = model
        self._secret = secret_fn
        self._apply = apply_fn
        self._ready = ready_fn
        self._begin = begin_fn
        self.seats = list(seats)
        self.code = (code or _mk_code(rng)).upper()
        self._by_name = {}            # name -> seat
        self._tokens = {}             # seat -> token
        self._names = {}              # seat -> name
        self._ready_seats = set()
        self._seen = {}               # seat -> last-seen monotonic
        self._q = _queue.Queue()      # (seat, action) inbound
        self._ver = {s: 0 for s in seats}
        self._lock = threading.Lock()
        self.gate = False             # BoardRun sets True while animating
        self.last_error = None        # (reason, ip) for the lobby
        self.winner = None

    # -------- HTTP-thread API (thread-safe; never mutate the model here) ----
    def join(self, code, name):
        with self._lock:
            if code.upper() != self.code:
                return {"error": "wrong_code"}
            if name in self._by_name:
                return {"error": "name_taken"}
            free = [s for s in self.seats if s not in self._tokens]
            if not free:
                return {"error": "full"}
            seat = free[0]; token = _tok()
            self._by_name[name] = seat; self._tokens[seat] = token
            self._names[seat] = name; self._seen[seat] = time.monotonic()
            self._bump(seat)
            return {"seat": seat, "token": token}

    def _auth(self, seat, token):
        return seat in self._tokens and self._tokens[seat] == token

    def submit(self, seat, token, action):
        if not self._auth(seat, token):
            return {"error": "bad_token"}
        self._seen[seat] = time.monotonic()
        self._q.put((seat, action))
        return {"ok": True}

    def poll(self, seat, token, since):
        if not self._auth(seat, token):
            return {"error": "bad_token"}
        self._seen[seat] = time.monotonic()
        with self._lock:
            v = self._ver[seat]
            if v <= since:
                return {"v": v, "changed": False}
            return {"v": v, "view": self._secret(self.model, seat)}

    # ------------------------------ game-thread API ------------------------
    def pump(self):
        """Apply at most one queued action to the model. Gated: while `gate`
        is set (cabinet animating) nothing is applied. Returns applied
        results (0 or 1) for the caller to animate."""
        if self.gate:
            return []
        try:
            seat, action = self._q.get_nowait()
        except _queue.Empty:
            return []
        kind = action.get("kind")
        results = []
        if kind == "ready":
            if self._ready(self.model, seat, action):
                self._ready_seats.add(seat)
                if set(self.seats) <= self._ready_seats:
                    self._begin(self.model)
                self._bump_all()
        elif kind == "fire":
            if self.model.turn == seat:            # turn-gate on the authority
                res = self._apply(self.model, seat, action)
                if res is not None:
                    results.append(res)
                    self.winner = self.model.winner
                    self._bump_all()
        elif kind == "cancel":
            pass
        return results

    def connected(self, seat, timeout=6.0):
        t = self._seen.get(seat)
        return t is not None and (time.monotonic() - t) < timeout

    def status(self):
        with self._lock:
            return {"code": self.code,
                    "seats": [{"seat": s, "name": self._names.get(s),
                               "ready": s in self._ready_seats,
                               "connected": self.connected(s)}
                              for s in self.seats],
                    "last_error": self.last_error}

    # ------------------------------------------------- internals
    def _bump(self, seat):
        self._ver[seat] += 1
    def _bump_all(self):
        with self._lock:
            for s in self.seats:
                self._ver[s] += 1

def _mk_code(rng):
    import random as _r
    r = rng or _r.Random()
    return "".join(r.choice("ABCDEFGHJKLMNPRSTUVWXYZ2345679") for _ in range(4))
```

- [ ] **Step 4: Run tests, watch pass** — `secrecy invariant OK / join rules OK / turn gate + versions OK`.

- [ ] **Step 5: Commit** — `git commit -am "feat(board): SecretLocalSession (seats, tokens, turn-gated pump, versioned poll)"`

---

## Increment 3 — stdlib long-poll server + QR + port pick

### Task 3: `server.py` + `qr.py` + loopback round-trip test

**Files:** Create `games/board/companion/server.py`, `games/board/companion/qr.py`; modify `requirements.txt`; extend `tools/test_companion.py`.

**Interfaces:**
- Produces: `CompanionServer(session, app_html_path, *, preferred=1983, host="0.0.0.0")` with `.start() -> (host, port)`, `.stop()`, `.url(lan_ip)`; `pick_port(preferred, host) -> int`; `qr.matrix(url) -> list[list[bool]]`.
- Routes: `GET /` → app.html; `GET /app.js`? (inlined, so just `/`); `POST /join`, `GET /poll`, `POST /action`, `GET /status`.

- [ ] **Step 1 (test):** start `CompanionServer` on loopback with a fake session, then use `urllib` to `POST /join`, `POST /action {ready}`, `GET /poll` and assert JSON round-trips + `wrong_code` rejection. (Full test code written at implementation.)
- [ ] **Step 2:** run → fail (no module).
- [ ] **Step 3:** implement `server.py` (a `ThreadingHTTPServer` subclass + a `BaseHTTPRequestHandler` dispatching the routes to `session.join/submit/poll/status`; long-poll = loop `poll(since)` with `time.sleep(0.1)` up to ~25s; JSON in/out helpers; serve `app.html` bytes). `pick_port` tries `preferred`, then `preferred+1..+20`, then `bind(0)`. `qr.py` uses `segno.make(url).matrix` with a text-only fallback flag.
- [ ] **Step 4:** run → pass.
- [ ] **Step 5:** commit — `feat(board): stdlib long-poll companion server + QR + port fallback`.

---

## Increment 4 — phone client `app.html`

### Task 4: host-agnostic single-file client

**Files:** Create `games/board/phone/app.html`. Verify manually (served by the server).

**Interfaces:** talks to its own origin: `POST /join`, `GET /poll?seat=&token=&v=`, `POST /action`. State in `localStorage`: `{code, seat, token}` for reconnect.

Screens & behaviour (implementation writes full HTML/CSS/JS):
- **join**: name field (code from `?code=` query, prefilled); `POST /join` → store token; on `wrong_code|full|name_taken` show the reason.
- **place**: 10×10 grid; drag-to-place with rotate, plus **Auto** (client-side random that mirrors the fleet sizes) and **Ready** → `POST /action {kind:"ready", layout}`.
- **play**: renders from the polled `secret_view` — your turn: tap enemy cell → **FIRE** `POST /action {kind:"fire",x,y}`; not your turn: "opponent's turn", show your fleet + incoming.
- **over**: win/lose; the long-poll continues so both see the result.
- **reconnect**: on load, if `localStorage` has a token, skip join and resume polling; server re-syncs from authority.
- **Commit** — `feat(board): host-agnostic phone client (join/place/play/reconnect)`.

---

## Increment 5 — cabinet integration (BoardRun, battleship run/renderer, main.py, theme, register)

### Task 5: `BoardRun` + battleship `game.py` run/renderer + registration + lobby

**Files:** Create `games/board/run.py`, finish `games/battleship/game.py`, create `games/battleship/__init__.py`, `games/battleship/achievements.py`; modify `games/__init__.py`, `game/theme.py`, `main.py`.

**Interfaces:**
- `BoardRun(GameRun)`: owns `model`, `AnimQueue`, and (in `SECRET_LOCAL`) a `SecretLocalSession` + `CompanionServer`. `update(dt,inp)`: advance anim; when idle set `session.gate=False` and `pump()`; for each applied result, `session.gate=True` and enqueue its animation (with an `on_done` that clears the gate). `draw`/`draw_hud`: public board + lobby overlay.
- `BattleshipRun(BoardRun)` supplies: `apply_fn=model.fire`-wrapper, `ready_fn` (apply the phone's `layout`, validated with `model.place_ship`), `begin_fn=model.begin_fire`, plus the public voxel renderer + missile-arc anim + HUD.
- `INFO = GameInfo("battleship","BATTLESHIP","Hidden fleets, one shot a turn.", showcase_sprite="ship_vanguard", modes=[("secret","SECRET LOCAL"),("ai","VS AI"),("hotseat","HOTSEAT")], has_scores=False, music_pool="game")`.
- `games/__init__.py`: add `("BOARD", ["battleship"])` to `CATEGORIES`.
- `game/theme.py` GAMES: `"battleship": Theme(COBALT, FROST, COBALT)`.
- **`main.py`: no new App state and no edits required for the core flow** (confirmed via the codebase map). A `SECRET_LOCAL` run is created by the generic `start_run` (`main.py:664`), runs inside the existing `PLAYING` state, is drawn by the generic `run.draw`/`run.draw_hud` dispatch (`main.py:1727`, `1777`), and receives cabinet keys via the `handle_key` hook (`main.py:548`). So `BattleshipRun` self-manages its internal phases (lobby → placing → fire → over) and draws the QR/lobby + waiting/failure states itself in `draw_hud` (QR via `o.image()` from a rendered `pygame.Surface`). `has_scores=False` (like `studio`) keeps it out of the score/initials/replay machinery; `run_over=False` + an internal end screen (Esc → pause → exit) avoids the `RUN_END`/leaderboard path entirely. Registration edits only: `games/__init__.py` (BOARD category) and `game/theme.py` (naval signature).
- **Cabinet input for VS-AI/HOTSEAT** (secret-local takes no cabinet input — phones drive): a keyboard/gamepad cursor via the `handle_key` hook + `inp` (arrows move the cursor on the enemy grid, Enter/Space fires). No `MOUSEBUTTONDOWN` addition needed (the engine has none today).

- [ ] Sub-steps: (a) `game/theme.py` signature + `games/__init__.py` BOARD category (cabinet shows battleship, tiny commit). (b) `BoardRun` + `BattleshipRun` VS-AI mode first (no phones — proves the run/renderer/anim path in isolation, testable without a browser). (c) add `SECRET_LOCAL`: wire session + server + lobby overlay. (d) public renderer polish (voxel grids, missile arc, splash). Commit after each.

---

## Increment 6 — board-move replay with per-perspective playback

### Task 6: record the move stream; re-watch as any player's view

**Files:** Create `games/board/replay.py`; extend `tools/test_companion.py`; modify `main.py` (replay browser gains a perspective picker for board games).

**Interfaces:**
- `BoardReplayRecorder(game_id, mode, seed)`: `.placement(seat, layout)`, `.move(seat, action)`, `.build(winner)` → `{schema, kind:"board", game, mode, seed, placements, moves, winner, created}`.
- `BoardReplay(data)`: `.rebuild_to(step) -> model` (fresh `BattleshipModel(Random(seed))`, apply placements + first `step` moves) and `.view(step, perspective)` → `secret_view(model, perspective)` for `"P1"/"P2"`, or `public_view(model)` for `"omniscient"` (director; reveals both — spectator mode explicitly allowed since the match is over).
- Test: rebuild at each step is deterministic; `view(step,"P1")` never exposes P2's un-hit ships at that step (the secrecy invariant holds *through time*), while `"omniscient"` may.
- **Self-contained, no `main.py` edits:** because `has_scores=False` hides the cabinet's REPLAYS menu (and its input-bitmask `REPLAYING` path doesn't fit move-stream replays anyway), the perspective viewer lives *inside* `BattleshipRun`: after a match, `R` enters an internal rewatch phase that steps the recorded move stream and draws `secret_view(step, perspective)` / `public_view` with the same renderer as live; keys `1/2/3` toggle `P1 / P2 / DIRECTOR`. The recorder auto-saves the last match to `replays/` as a `kind:"board"` JSON (distinct from the input-bitmask replays, skipped by the existing browser's loader).
- **Commit** — `feat(board): move-stream replays with per-player perspective playback`.

---

## Self-review notes

- **Spec coverage:** companion phones (I1–I5), Model B phone-controller (I4), self-host + host-agnostic client (I3–I4), general seam (I1–I2 game-agnostic session/views), opponent-up-front + graceful lobby (I5), port 1983 + fallback + manual (I3/I5), long-poll transport & typed rejects (I2–I3), secrecy invariant test (I1), reconnect (I2/I4), replay tie-in — **upgraded** to per-perspective playback per the user (I6).
- **Deviations from spec:** replay is now a first-class per-perspective feature (I6), not "free"; the spec's replay paragraph is corrected in the docs step. VS-AI is built first within I5 as a no-browser proving ground for the run/renderer.
- **Risk order:** headless correctness core (I1–I2) is locked and tested before any GL/network/browser work; each increment is independently committable.
