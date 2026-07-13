"""Battleship — the cabinet-side game module (BOARD category).

Rules live in games/battleship/model.py; this module is the cabinet's view of
them. It starts with the two projection functions that ARE the secrecy
boundary; the BoardRun subclass, public renderer, INFO and create_run are
added by the cabinet-integration increment.

    public_view(model)       -> what the shared cabinet TV may draw
                                 (shot history + sunk ships; never an un-hit ship)
    secret_view(model, seat) -> the public board PLUS only `seat`'s own fleet
                                 (what that one phone may see)

The invariant that makes "truly secret" true: neither public_view nor any
secret_view for seat S contains hidden state belonging to another seat — for
Battleship, an opponent's un-hit, un-sunk ship cells never appear.
"""
import os

from arcade.game_api import GameInfo, GameRun
from game.theme import (TEXT, DIM, EMBER, GOLD, WARN, DANGER, GOOD, PANEL,
                        PANEL_DIM, HAIR, COBALT, FROST, RUST)
from games.board.anim import Anim, AnimQueue, ease_out, lerp
from games.board.companion import qr
from games.board.companion.server import CompanionServer, DEFAULT_PORT
from games.board.companion.session import SecretLocalSession
from games.board.replay import BoardReplay, BoardReplayRecorder, save as _save_replay
from games.battleship.model import BattleshipModel, PLAYERS

_APP_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "board", "phone", "app.html")

# board colours (naval Emberlight signature)
_SEA = (24, 40, 56, 255)
_SEA_LINE = (40, 62, 84, 255)
_MISS = (120, 120, 120, 255)
_HIT = RUST
_SUNK = (150, 54, 62, 255)
_SHIP = (91, 155, 213, 255)     # own/revealed ship (replay only; never live public)


def _shot_markers(model, target):
    """Public record of shots that have landed on `target`: each fired cell
    tagged hit/miss. Only *fired* cells appear — an un-fired ship cell is never
    revealed, which is exactly fog-of-war."""
    out = []
    for cell in model.shots[target]:
        x, y = cell[0], cell[1]
        out.append({"x": x, "y": y,
                    "hit": model.ship_at(target, x, y) is not None})
    return out


def _sunk_ships(model, player):
    """`player`'s fully-sunk ships, revealed with their cells (sinking is
    announced publicly in Battleship)."""
    return [{"name": s["name"], "cells": [list(c) for c in s["cells"]]}
            for s in model.ships[player] if model.is_sunk(player, s)]


def public_view(model):
    """Everything the shared cabinet screen may draw. Contains no un-hit ship
    for either side."""
    return {
        "size": model.size,
        "phase": model.phase,
        "turn": model.turn,
        "winner": model.winner,
        "boards": {
            p: {
                "shots": _shot_markers(model, p),   # shots that landed on p
                "sunk": _sunk_ships(model, p),      # p's sunk ships (revealed)
                "afloat": model.remaining_ships(p),
            }
            for p in PLAYERS
        },
    }


def secret_view(model, seat):
    """What ONE seat's phone may see: the public board, plus ONLY this seat's
    own fleet (its secret). Adds nothing about the opponent beyond what's
    already public."""
    view = public_view(model)
    view["you"] = seat
    view["your_turn"] = (model.phase == "fire" and model.turn == seat
                         and model.winner is None)
    view["your_fleet"] = [
        {
            "name": s["name"],
            "cells": [list(c) for c in s["cells"]],
            "hits": [[x, y] for x, y in s["cells"]
                     if model.already_shot(seat, x, y)],
            "sunk": model.is_sunk(seat, s),
        }
        for s in model.ships[seat]
    ]
    return view


# ===========================================================================
# Cabinet run — SECRET LOCAL mode (companion phones; the cabinet is the TV).
# ===========================================================================
INFO = GameInfo(
    "battleship", "BATTLESHIP",
    "Hidden fleets, secret phones, one shot a turn.",
    showcase_sprite="ship_vanguard",
    modes=[("secret", "SECRET LOCAL")],
    has_scores=False,      # win/lose, not a score — stays out of initials/replay flow
    attract=False,
    game_music=True,
    music_pool="game",
)

_COLS = "ABCDEFGHIJ"


# --- session hooks (game-thread only; supplied to SecretLocalSession) -------
def _apply_move(model, seat, action):
    if action.get("kind") == "fire":
        return model.fire(seat, action["x"], action["y"])
    return None


def _commit_fleet(model, seat, action):
    """Apply the phone's fleet layout, validating each ship on the authority.
    Rejects (returns False) a partial/illegal layout so the phone can resend."""
    layout = action.get("layout") or []
    model.ships[seat] = []
    for s in layout:
        if not model.place_ship(seat, s["name"], int(s["size"]),
                                int(s["x"]), int(s["y"]), bool(s["horizontal"])):
            model.ships[seat] = []
            return False
    return model.fleet_complete(seat)


def _begin_fire(model):
    model.begin_fire("P1")


class BattleshipRun(GameRun):
    """Cabinet side of a secret-local Battleship match. The model is the
    authority; phones are private controllers; this run pumps the session on
    the game thread, animates each move on the shared TV, and renders only the
    public projection (never a hidden ship)."""

    def __init__(self, mode, rng):
        self.mode = mode or "secret"
        self.rng = rng
        self.model = BattleshipModel(rng)
        self.anim = AnimQueue()
        self.events = []
        self.time = 0.0

        # profile hooks (attach_profile fills these)
        self.section = None
        self.settings = None
        self.save_cb = lambda: None

        # match recorder (feeds the per-perspective replay)
        self._rec = BoardReplayRecorder("battleship", self.mode)
        self._last_replay = None

        # secret-local infra — hooks also record placements/moves as they apply
        def _apply(model, seat, action):
            res = _apply_move(model, seat, action)
            if res is not None:
                self._rec.move(seat, action["x"], action["y"])
            return res

        def _ready(model, seat, action):
            ok = _commit_fleet(model, seat, action)
            if ok:
                self._rec.placement(seat, action.get("layout") or [])
            return ok

        self.session = SecretLocalSession(
            self.model, secret_fn=secret_view, apply_fn=_apply,
            ready_fn=_ready, begin_fn=_begin_fire, rng=rng)
        self.server = None
        self.host_error = None
        self._qr_surf = None

        # replay rewatch state (entered with R on the over screen)
        self.replay = None
        self.replay_step = 0
        self.perspective = "P1"
        self.replay_playing = False
        self._replay_timer = 0.0

        # cached snapshots for draw (built each update on the game thread)
        self._public = public_view(self.model)
        self._status = self.session.status()

    # ------------------------------------------------------- cabinet contract
    @property
    def score(self):
        return 0

    @property
    def run_over(self):
        return False        # match end is handled in-run (Esc to leave)

    def attach_profile(self, section, settings, save_cb):
        self.section = section
        self.settings = settings
        self.save_cb = save_cb
        self._ensure_server()

    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out, self.events = self.events, []
        return out

    def run_stats(self):
        return {}

    def run_summary(self):
        return {"win": self.model.winner is not None}

    def handle_key(self, key):
        # During play the phones drive; the cabinet only takes keys on the
        # over screen, to enter/steer the per-perspective replay.
        import pygame
        if self.model.phase != "over":
            return False
        if self.replay is None:
            if key == pygame.K_r and self._last_replay is not None:
                self.replay = BoardReplay(self._last_replay)
                self.replay_step = self.replay.total
                self.perspective = "P1"
                self.replay_playing = False
            return True
        if key == pygame.K_r:
            self.replay = None
        elif key == pygame.K_1:
            self.perspective = "P1"
        elif key == pygame.K_2:
            self.perspective = "P2"
        elif key == pygame.K_3:
            self.perspective = "director"
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.replay_step = max(0, self.replay_step - 1)
            self.replay_playing = False
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.replay_step = min(self.replay.total, self.replay_step + 1)
            self.replay_playing = False
        elif key == pygame.K_SPACE:
            if self.replay_step >= self.replay.total:
                self.replay_step = 0
            self.replay_playing = not self.replay_playing
        return True

    def close(self):
        if self.server is not None:
            try:
                self.server.stop()
            except Exception:
                pass
            self.server = None

    def __del__(self):
        self.close()

    # --------------------------------------------------------------- server
    def _ensure_server(self):
        if self.mode != "secret" or self.server is not None or self.host_error:
            return
        forced = 0
        if self.settings:
            try:
                forced = int(self.settings.get("board_port", 0) or 0)
            except (TypeError, ValueError):
                forced = 0
        try:
            self.server = CompanionServer(
                self.session, app_html_path=_APP_HTML,
                preferred=forced or DEFAULT_PORT)
            self.server.start(forced_port=forced or None)
        except OSError as e:
            self.server = None
            self.host_error = str(e)

    def _qr_surface(self):
        """Render the join URL to a cached pygame Surface for o.image()."""
        if self._qr_surf is not None:
            return self._qr_surf
        if not self.server:
            return None
        import pygame
        mat = qr.matrix(self.server.url())
        if not mat:
            return None
        n = len(mat)
        quiet, scale = 4, 6
        px = (n + quiet * 2) * scale
        surf = pygame.Surface((px, px))
        surf.fill((243, 231, 212))            # warm light quiet-zone
        dark = (18, 12, 9)
        for yy, row in enumerate(mat):
            for xx, v in enumerate(row):
                if v:
                    surf.fill(dark, ((xx + quiet) * scale, (yy + quiet) * scale,
                                     scale, scale))
        self._qr_surf = surf
        return surf

    # --------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        if self.replay is not None:                 # rewatching a finished match
            if self.replay_playing:
                self._replay_timer += dt
                if self._replay_timer >= 0.55:
                    self._replay_timer = 0.0
                    if self.replay_step < self.replay.total:
                        self.replay_step += 1
                    else:
                        self.replay_playing = False
            return
        self._ensure_server()
        self.anim.update(dt)
        if not self.anim.busy:
            self.session.gate = False
            for res in self.session.pump():
                self._on_move(res)
        self._public = public_view(self.model)
        self._status = self.session.status()

    def _on_move(self, res):
        """A fire was applied on the authority; play it out on the TV before
        the next move (the anim queue gates the session via `gate`)."""
        self.session.gate = True

        def done(_a):
            self.session.gate = False

        self.anim.add(Anim("missile", 0.62, data=res, ease=ease_out, on_done=done))
        self.emit("bs_shot", **res)
        if res.get("win"):
            self._last_replay = self._rec.build(self.model.winner)
            try:
                _save_replay(self._last_replay)
            except OSError:
                pass

    def on_event(self, etype, data, renderer, audio, banner):
        if etype != "bs_shot":
            return
        if data.get("hit"):
            audio.play("powerup")
            renderer.add_aberration(0.4)
        else:
            audio.play("menu_move")
        if data.get("sunk"):
            banner(f"{data['sunk'].upper()} SUNK", 1.6)
            audio.play("toast")
        if data.get("win"):
            winner = data["shooter"]
            banner(f"{self._name(winner)} WINS", 2.4)

    # ------------------------------------------------------------- rendering
    def draw(self, renderer, section):
        renderer.draw_scene(_EmptyBatch(), walls=False, stars=True)

    def draw_hud(self, o, width, height, section):
        o.text("BATTLESHIP", width / 2, 24, size=30, color=COBALT, center=True)
        if self.replay is not None:
            return self._draw_replay(o, width, height)
        if self.host_error:
            return self._draw_host_error(o, width, height)
        if self.model.phase == "place":
            return self._draw_lobby(o, width, height)
        self._draw_boards(o, width, height)
        if self.model.phase == "over":
            self._draw_over(o, width, height)

    # -- lobby / waiting + failure states
    def _draw_lobby(self, o, width, height):
        seats = self._status["seats"]
        both_joined = all(s["name"] for s in seats)
        cx = width / 2
        if self.server and not both_joined:
            surf = self._qr_surface()
            if surf is not None:
                o.image("bs_qr", surf, cx - 260, 130, scale=0.62)
            o.text("SCAN TO JOIN", cx - 130, 150, size=16, color=DIM)
            o.text(self.server.url().split("?")[0], cx - 130, 180, size=15,
                   color=TEXT)
            o.text("code", cx - 130, 220, size=13, color=DIM)
            o.text(self.session.code, cx - 130, 236, size=40, color=GOLD)
        elif not self.server:
            o.text("Starting host…", cx, 160, size=18, color=DIM, center=True)

        # seat roster
        o.text("PLAYERS", cx + 150, 150, size=13, color=DIM)
        for i, s in enumerate(seats):
            y = 180 + i * 46
            if not s["name"]:
                o.text(f"{s['seat']}   waiting to join…", cx + 150, y,
                       size=20, color=DIM)
                continue
            state = "ready" if s["ready"] else ("here" if s["connected"]
                                                else "reconnecting…")
            col = GOOD if s["ready"] else TEXT
            o.text(f"{s['seat']}  {s['name']}", cx + 150, y, size=20, color=col)
            o.text(state, cx + 380, y, size=16,
                   color=GOOD if s["ready"] else DIM)

        msg = "Match starts when both fleets are placed"
        err = self._status.get("last_error")
        if err and not both_joined:
            reason = {"wrong_code": "a device tried the wrong code",
                      "full": "a device tried to join a full match"}.get(err[0], err[0])
            msg = f"⚠ {reason} (from {err[1]})  ·  still open"
        o.text(msg, width / 2, height - 70, size=15,
               color=WARN if (err and not both_joined) else DIM, center=True)
        o.text("Esc: cancel and leave", width / 2, height - 44, size=13,
               color=DIM, center=True)

    def _draw_host_error(self, o, width, height):
        cx = width / 2
        o.rect(cx - 300, 200, 600, 160, PANEL)
        o.text("COULDN'T HOST", cx, 240, size=26, color=DANGER, center=True)
        o.text(self.host_error, cx, 290, size=15, color=TEXT, center=True)
        o.text("Set a different port in Settings (board_port) and relaunch.",
               cx, 330, size=14, color=DIM, center=True)
        o.text("Esc: leave", cx, height - 44, size=13, color=DIM, center=True)

    # -- the shared board (fire / over)
    def _draw_boards(self, o, width, height):
        cell = 34
        gw = cell * self.model.size
        gap = 90
        top = 150
        left_x = width / 2 - gw - gap / 2
        right_x = width / 2 + gap / 2
        # left = P1's waters, right = P2's waters
        self._draw_grid(o, left_x, top, cell, "P1", )
        self._draw_grid(o, right_x, top, cell, "P2")
        # turn / status banner
        if self.model.phase == "fire":
            turn = self.model.turn
            o.text(f"{self._name(turn)} — taking aim on their phone",
                   width / 2, top + gw + 40, size=20, color=EMBER, center=True)
        self._draw_missile(o, left_x, right_x, top, cell)

    def _draw_grid(self, o, ox, oy, cell, seat, board=None, reveal=None):
        board = board if board is not None else self._public["boards"][seat]
        marks = {}
        for s in board["shots"]:
            marks[(s["x"], s["y"])] = "hit" if s["hit"] else "miss"
        for ship in board["sunk"]:
            for c in ship["cells"]:
                marks[(c[0], c[1])] = "sunk"
        n = self.model.size
        o.text(f"{self._name(seat)}'s waters", ox, oy - 28, size=17, color=COBALT)
        for y in range(n):
            for x in range(n):
                rx, ry = ox + x * cell, oy + y * cell
                k = marks.get((x, y))
                if k:
                    col = {"miss": _MISS, "hit": _HIT, "sunk": _SUNK}[k]
                elif reveal and (x, y) in reveal:
                    col = _SHIP                       # revealed ship (replay only)
                else:
                    col = _SEA
                o.rect(rx + 1, ry + 1, cell - 2, cell - 2, col)
        afloat = board["afloat"]
        o.text(f"{afloat} ship{'s' if afloat != 1 else ''} afloat", ox,
               oy + n * cell + 8, size=14, color=DIM if afloat else DANGER)

    # -- per-perspective replay (rewatch a finished match)
    def _draw_replay(self, o, width, height):
        view = self.replay.view(self.replay_step, self.perspective)
        cell = 34
        gw = cell * self.model.size
        gap = 90
        top = 150
        left_x = width / 2 - gw - gap / 2
        right_x = width / 2 + gap / 2
        reveal = self._reveal_sets(view)
        self._draw_grid(o, left_x, top, cell, "P1",
                        board=view["boards"]["P1"], reveal=reveal.get("P1"))
        self._draw_grid(o, right_x, top, cell, "P2",
                        board=view["boards"]["P2"], reveal=reveal.get("P2"))
        plabel = {"P1": f"{self._name('P1')}'s view",
                  "P2": f"{self._name('P2')}'s view",
                  "director": "DIRECTOR — both fleets revealed"}[self.perspective]
        o.text(f"REPLAY · {plabel}", width / 2, top + gw + 40, size=20,
               color=GOLD, center=True)
        state = "▶ playing" if self.replay_playing else "❙❙ paused"
        o.text(f"move {self.replay_step}/{self.replay.total}    {state}",
               width / 2, top + gw + 70, size=15, color=DIM, center=True)
        o.text("1/2/3: P1 · P2 · Director     ←/→: step     "
               "Space: play/pause     R: exit replay",
               width / 2, height - 44, size=13, color=DIM, center=True)

    def _reveal_sets(self, view):
        """Which ship cells to reveal per grid for the current perspective:
        your own fleet for P1/P2, both fleets for the director."""
        out = {}
        if view.get("perspective") == "director":
            for p in ("P1", "P2"):
                out[p] = {tuple(c) for s in view["fleets"][p] for c in s["cells"]}
        else:
            you = view.get("you")
            if you:
                out[you] = {tuple(c) for s in view.get("your_fleet", [])
                            for c in s["cells"]}
        return out

    def _draw_missile(self, o, left_x, right_x, top, cell):
        cur = self.anim.current
        if cur is None or cur.kind != "missile":
            return
        res = cur.data
        ox = left_x if res["target"] == "P1" else right_x
        tx = ox + res["x"] * cell + cell / 2
        ty = top + res["y"] * cell + cell / 2
        p = cur.p
        # arc a bright ember down onto the target cell
        sx = tx
        sy = lerp(top - 70, ty, p)
        size = 10 if p < 0.9 else 22       # flare on impact
        col = GOLD if p < 0.9 else (_HIT if res["hit"] else _MISS)
        o.rect(sx - size / 2, sy - size / 2, size, size, col)

    def _draw_over(self, o, width, height):
        w = self.model.winner
        o.text(f"\U0001f3c6  {self._name(w)} WINS", width / 2, height - 96,
               size=30, color=GOLD, center=True)
        o.text("Esc: leave", width / 2, height - 46, size=14, color=DIM,
               center=True)

    # ------------------------------------------------------------- helpers
    def _name(self, seat):
        for s in self._status["seats"]:
            if s["seat"] == seat and s["name"]:
                return s["name"]
        return seat


class _EmptyBatch:
    """A Batcher-shaped empty payload so draw_scene renders just the backdrop
    without importing the GL Batcher into this module."""
    batches = {}
    late_cubes = []


def create_run(mode, rng):
    return BattleshipRun(mode, rng)

