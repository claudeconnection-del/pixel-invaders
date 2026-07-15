"""Solitaire (Klondike) — the cabinet-side game module (TABLETOP category).

Rules live in games/solitaire/model.py; this is the table: a 2D overlay view
drawn over a felt backdrop (solid/gradient wash, or a living ambient-scene
felt), with mouse pointer-picking (click a card to pick up a run, click a
destination to drop; double-click sends a card home). Keyboard shortcuts cover
undo / autoplay / new deal. Achievements + grind counters + skin selection are
wired in later increments; this increment makes it playable.
"""
import random

import pygame

from arcade.game_api import GameInfo, GameRun
from game import theme
from game.theme import TEXT, DIM, EMBER, GOLD, PANEL
from render.renderer import Batcher
from ambient import scenes as ambient_scenes
from ambient.preset import AmbientPreset
from games.cards import render as card_render
from games.cards import skins
from games.cards.deck import SUITS, Card
from games.solitaire.achievements import ACHIEVEMENTS as _SOL_ACHIEVEMENTS
from games.solitaire.model import Solitaire

INFO = GameInfo(
    "solitaire", "SOLITAIRE",
    "Klondike — clear the tableau, build the foundations.",
    showcase_sprite="cube",
    modes=[("draw1", "DRAW ONE"), ("draw3", "DRAW THREE")],
    has_scores=False, attract=False, game_music=True, music_pool="menu",
)

ACHIEVEMENTS = _SOL_ACHIEVEMENTS
_GRIND_KEYS = ("sol_games", "sol_wins", "sol_streak", "sol_best_streak",
               "sol_best_time")

# table layout (logical UI units; the table is centred in the full width)
CARD_W, CARD_H = 96, 132
GAP = 20
COL_STRIDE = CARD_W + GAP
TABLE_W = 7 * CARD_W + 6 * GAP
TOP_Y = 96
TABLEAU_TOP = TOP_Y + CARD_H + 30
FAN_DOWN, FAN_UP = 18, 30
FOUNDATION_COLS = [3, 4, 5, 6]           # top-row columns holding the 4 suits
_SUIT_NAME = {"S": "spades", "H": "hearts", "D": "diamonds", "C": "clubs"}


class SolitaireRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode or "draw1"
        self.draw_count = 3 if self.mode == "draw3" else 1
        self.rng = rng
        self.model = Solitaire(self.draw_count).deal(rng)
        self.time = 0.0
        self.events = []
        self.section = None
        self.settings = None
        self.save_cb = lambda: None

        self.deck = skins.deck_by_id("classic")
        self.felt = skins.felt_by_id("emberlight")
        self._felt_preset = AmbientPreset(
            "felt", "felt", self.felt.scene or "nebula",
            [list(c) for c in self.felt.colors], speed=0.5, density="medium")

        self.sel = None            # current selection (source)
        self._prev_mb = False
        self._last_click = None    # (target, time) for double-click detection
        self._hover = None
        self.won_flag = False
        self._W, self._H = 1280, 860

        # skin customization panel (TAB) — deck + felt, shared across tabletop
        self.customize = False
        self.custom_row = 0        # 0 = Deck, 1 = Felt

    # ------------------------------------------------------ cabinet contract
    @property
    def score(self):
        return self.model.cards_home

    @property
    def run_over(self):
        return False               # solo table; Esc leaves via the cabinet

    def attach_profile(self, section, settings, save_cb):
        self.section = section
        self.settings = settings
        self.save_cb = save_cb
        tt = self._tt()
        self.deck = skins.deck_by_id(tt.get("deck", "classic"))
        self._set_felt(skins.felt_by_id(tt.get("felt", "emberlight")))
        life = section["lifetime"]
        for k in _GRIND_KEYS:
            life.setdefault(k, 0)
        life["sol_games"] += 1          # this freshly-dealt game counts as played
        self._sync_unlocks()
        self.save_cb()

    def _tt(self):
        """The shared tabletop cosmetics store (settings['tabletop']), with
        defaults backfilled for old saves."""
        tt = (self.settings or {}).setdefault("tabletop", {}) \
            if self.settings is not None else {}
        tt.setdefault("deck", "classic")
        tt.setdefault("felt", "emberlight")
        tt.setdefault("unlocked_decks", [])
        tt.setdefault("unlocked_felts", [])
        return tt

    def _set_felt(self, felt):
        self.felt = felt
        self._felt_preset = AmbientPreset(
            "felt", "felt", felt.scene or "nebula",
            [list(c) for c in felt.colors], speed=0.5, density="medium")

    def _avail_decks(self):
        return skins.available_decks(set(self._tt().get("unlocked_decks", [])))

    def _avail_felts(self):
        return skins.available_felts(set(self._tt().get("unlocked_felts", [])))

    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out, self.events = self.events, []
        return out

    def run_stats(self):
        return {"time": self.time, "moves": self.model.moves,
                "undos": self.model.undo_count, "won": self.model.won}

    def _sync_unlocks(self):
        """Mirror any earned cosmetic-unlock achievements into the shared
        tabletop store so the tied premium deck/felt becomes selectable."""
        if self.section is None or self.settings is None:
            return
        tt = self._tt()
        got = set(self.section.get("achievements", {}).keys())
        changed = False
        for d in skins.DECKS:
            if d.premium in got and d.id not in tt["unlocked_decks"]:
                tt["unlocked_decks"].append(d.id)
                changed = True
        for f in skins.FELTS:
            if f.premium in got and f.id not in tt["unlocked_felts"]:
                tt["unlocked_felts"].append(f.id)
                changed = True
        if changed:
            self.save_cb()

    def run_summary(self):
        return {"win": self.model.won}

    # ------------------------------------------------------------- input
    def update(self, dt, inp):
        self.time += dt                     # felt keeps animating even in panel
        self._sync_unlocks()                # grant cosmetics as achievements land
        mb = pygame.mouse.get_pressed()[0] if pygame.get_init() else False
        if not self.customize and mb and not self._prev_mb:
            self._click(inp.aim_x, inp.aim_y)
        self._prev_mb = mb
        self._hover = None if self.customize else self._hit(inp.aim_x, inp.aim_y)

    def handle_key(self, key):
        if self.customize:
            self._panel_key(key)
            return True
        if key == pygame.K_TAB:             # open the skin picker (deck + felt)
            self.customize = True
            self.custom_row = 0
        elif key in (pygame.K_u, pygame.K_z):
            if self.model.undo():
                self.emit("sol_undo")
        elif key == pygame.K_SPACE:
            if self.model.collect_to_foundations():
                self.emit("sol_home")
                self._check_win()
        elif key == pygame.K_n:
            self._new_deal()
        return True

    def _panel_key(self, key):
        if key == pygame.K_TAB:             # Esc is eaten by the cabinet (pause)
            self.customize = False
        elif key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
            self.custom_row = 1 - self.custom_row
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._cycle_skin(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._cycle_skin(1)

    def _cycle_skin(self, direction):
        tt = self._tt()
        if self.custom_row == 0:
            opts = self._avail_decks()
            i = next((k for k, d in enumerate(opts) if d.id == self.deck.id), 0)
            self.deck = opts[(i + direction) % len(opts)]
            tt["deck"] = self.deck.id
        else:
            opts = self._avail_felts()
            i = next((k for k, f in enumerate(opts) if f.id == self.felt.id), 0)
            self._set_felt(opts[(i + direction) % len(opts)])
            tt["felt"] = self.felt.id
        self.save_cb()
        self.emit("sol_move")

    def _new_deal(self):
        if self.section is not None and not self.won_flag:
            self.section["lifetime"]["sol_streak"] = 0   # gave up: streak breaks
        self.model = Solitaire(self.draw_count).deal(random.Random())
        self.sel = None
        self.won_flag = False
        if self.section is not None:
            self.section["lifetime"]["sol_games"] += 1
            self.save_cb()
        self.emit("sol_deal")

    def _click(self, px, py):
        t = self._hit(px, py)
        if t is None:
            self.sel = None
            return
        if t[0] == "stock":
            if self.model.draw():
                self.emit("sol_draw")
            self.sel = None
            return
        dbl = (self._last_click and self._last_click[0] == t
               and self.time - self._last_click[1] < 0.4)
        self._last_click = (t, self.time)

        if self.sel is None:
            self._select(t, dbl)
        else:
            self._drop(t)

    def _select(self, t, dbl):
        kind = t[0]
        if kind == "waste" and self.model.waste:
            if dbl and self.model.waste_to_foundation():
                self.emit("sol_home")
                self._check_win()
                return
            self.sel = {"kind": "waste"}
        elif kind == "tableau":
            col, k = t[1], t[2]
            p = self.model.tableau[col]
            if k == "empty":
                return
            ndown = len(p["down"])
            if k < ndown:            # a face-down card: not selectable
                return
            u = k - ndown
            if dbl and u == len(p["up"]) - 1 and self.model.tableau_to_foundation(col):
                self.emit("sol_home")
                self._check_win()
                return
            self.sel = {"kind": "tableau", "col": col, "count": len(p["up"]) - u}
        elif kind == "foundation" and self.model.foundations[t[1]]:
            self.sel = {"kind": "foundation", "suit": t[1]}

    def _drop(self, t):
        sel, moved, home = self.sel, False, False
        if t[0] == "tableau":
            j = t[1]
            if sel["kind"] == "waste":
                moved = self.model.waste_to_tableau(j)
            elif sel["kind"] == "tableau":
                moved = self.model.tableau_to_tableau(sel["col"], sel["count"], j)
            elif sel["kind"] == "foundation":
                moved = self.model.foundation_to_tableau(sel["suit"], j)
        elif t[0] == "foundation":
            if sel["kind"] == "waste":
                moved = home = self.model.waste_to_foundation()
            elif sel["kind"] == "tableau" and sel["count"] == 1:
                moved = home = self.model.tableau_to_foundation(sel["col"])
        self.sel = None
        if moved:
            self.emit("sol_home" if home else "sol_move")
            self._check_win()

    def _check_win(self):
        if self.model.won and not self.won_flag:
            self.won_flag = True
            if self.section is not None:
                life = self.section["lifetime"]
                life["sol_wins"] = life.get("sol_wins", 0) + 1
                life["sol_streak"] = life.get("sol_streak", 0) + 1
                life["sol_best_streak"] = max(life.get("sol_best_streak", 0),
                                              life["sol_streak"])
                t = int(self.time)
                if not life.get("sol_best_time") or t < life["sol_best_time"]:
                    life["sol_best_time"] = t
                self.save_cb()
            self.emit("sol_win")        # engine sees the updated counters here

    # ------------------------------------------------------------ hit-test
    def _ox(self):
        return max(20, (self._W - TABLE_W) / 2)

    def _col_x(self, i):
        return self._ox() + i * COL_STRIDE

    def _col_ys(self, i):
        p = self.model.tableau[i]
        ys, y = [], TABLEAU_TOP
        for _ in p["down"]:
            ys.append(y)
            y += FAN_DOWN
        for _ in p["up"]:
            ys.append(y)
            y += FAN_UP
        return ys

    def _hit(self, px, py):
        ox = self._ox()
        if _in(px, py, ox, TOP_Y, CARD_W, CARD_H):
            return ("stock",)
        wfan = CARD_W + (2 * 24 if self.draw_count == 3 else 0)
        if _in(px, py, ox + COL_STRIDE, TOP_Y, wfan, CARD_H):
            return ("waste",)
        for idx, col in enumerate(FOUNDATION_COLS):
            if _in(px, py, ox + col * COL_STRIDE, TOP_Y, CARD_W, CARD_H):
                return ("foundation", SUITS[idx])
        for i in range(7):
            cx = self._col_x(i)
            if not (cx <= px < cx + CARD_W):
                continue
            ys = self._col_ys(i)
            if not ys:
                if TABLEAU_TOP <= py < TABLEAU_TOP + CARD_H:
                    return ("tableau", i, "empty")
                return None
            for k in range(len(ys)):
                bottom = ys[k + 1] if k + 1 < len(ys) else ys[k] + CARD_H
                if ys[k] <= py < bottom:
                    return ("tableau", i, k)
        return None

    # ------------------------------------------------------------ drawing
    def draw(self, renderer, section):
        self._W, self._H = renderer.ui_w, renderer.ui_h
        b = Batcher()
        if self.felt.scene:
            fn = ambient_scenes.SCENES.get(self.felt.scene)
            if fn:
                fn(self._felt_preset, self.time, renderer, b)
            renderer.draw_scene(b, walls=False,
                                stars=ambient_scenes.SCENE_STARS.get(self.felt.scene, True))
        else:
            renderer.draw_scene(b, walls=False, stars=False)

    def _draw_felt_wash(self, o, W, H):
        f = self.felt
        if f.scene:
            o.rect(0, 0, W, H, (8, 8, 12, 70))         # gentle darken for contrast
            return
        cols = f.colors
        if f.kind == "solid" or len(cols) < 2:
            o.rect(0, 0, W, H, (cols[0][0], cols[0][1], cols[0][2], 255))
            return
        top, bot, n = cols[0], cols[-1], 24
        for k in range(n):
            t = k / (n - 1)
            c = (int(top[0] + (bot[0] - top[0]) * t),
                 int(top[1] + (bot[1] - top[1]) * t),
                 int(top[2] + (bot[2] - top[2]) * t), 255)
            o.rect(0, H * k / n, W + 2, H / n + 1, c)

    def draw_hud(self, o, width, height, section):
        o.offset_x = 0.0
        W, H = self._W, self._H
        ox = self._ox()
        self._draw_felt_wash(o, W, H)

        # stock
        if self.model.stock:
            card_render.draw_card(o, ox, TOP_Y, CARD_W, CARD_H, None, self.deck,
                                  face_up=False)
        else:
            card_render.draw_slot(o, ox, TOP_Y, CARD_W, CARD_H, "O")
        self._hover_mark(o, ("stock",), ox, TOP_Y, CARD_W, CARD_H)

        # waste (fan the last up-to-3)
        wx = ox + COL_STRIDE
        w = self.model.waste
        if not w:
            card_render.draw_slot(o, wx, TOP_Y, CARD_W, CARD_H)
        else:
            show = w[-3:] if self.draw_count == 3 else w[-1:]
            for j, card in enumerate(show):
                sel = (self.sel and self.sel["kind"] == "waste" and j == len(show) - 1)
                card_render.draw_card(o, wx + j * 24, TOP_Y, CARD_W, CARD_H,
                                      card, self.deck, selected=bool(sel))

        # foundations
        for idx, col in enumerate(FOUNDATION_COLS):
            suit = SUITS[idx]
            fx = ox + col * COL_STRIDE
            pile = self.model.foundations[suit]
            if pile:
                sel = self.sel and self.sel.get("suit") == suit
                card_render.draw_card(o, fx, TOP_Y, CARD_W, CARD_H, pile[-1],
                                      self.deck, selected=bool(sel))
            else:
                card_render.draw_slot(o, fx, TOP_Y, CARD_W, CARD_H, suit)
            self._hover_mark(o, ("foundation", suit), fx, TOP_Y, CARD_W, CARD_H)

        # tableau
        for i in range(7):
            self._draw_column(o, i)

        self._draw_footer(o, W, H)
        if self.won_flag:
            self._draw_win(o, W, H)
        if self.customize:
            self._draw_customize(o, W, H)

    def _draw_column(self, o, i):
        cx = self._col_x(i)
        p = self.model.tableau[i]
        ys = self._col_ys(i)
        if not ys:
            card_render.draw_slot(o, cx, TABLEAU_TOP, CARD_W, CARD_H)
            self._hover_mark(o, ("tableau", i, "empty"), cx, TABLEAU_TOP, CARD_W, CARD_H)
            return
        ndown = len(p["down"])
        nup = len(p["up"])
        sel_from = None
        if self.sel and self.sel.get("kind") == "tableau" and self.sel["col"] == i:
            sel_from = nup - self.sel["count"]          # up-index where selection starts
        cards = [(c, False) for c in p["down"]] + [(c, True) for c in p["up"]]
        for k, (card, up) in enumerate(cards):
            selected = up and sel_from is not None and (k - ndown) >= sel_from
            card_render.draw_card(o, cx, ys[k], CARD_W, CARD_H, card, self.deck,
                                  face_up=up, selected=selected)
        # hover highlight on the frontmost card of the column
        if self._hover and self._hover[0] == "tableau" and self._hover[1] == i:
            k = self._hover[2]
            if k != "empty":
                card_render.hover_outline(o, cx, ys[k], CARD_W, CARD_H)

    def _hover_mark(self, o, target, x, y, w, h):
        if self._hover == target:
            card_render.hover_outline(o, x, y, w, h)

    def _draw_footer(self, o, W, H):
        o.text(f"{self.model.cards_home}/52 home   moves {self.model.moves}",
               24, H - 34, size=15, color=DIM)
        o.text("Click: pick/drop   Double-click: send home   U: undo   "
               "Space: autoplay   N: new deal   Tab: skins",
               W / 2, H - 34, size=14, color=DIM, center=True)

    def _draw_customize(self, o, W, H):
        x, y0 = 90, 220
        pw, ph = 480, 232
        o.rect(x - 26, y0 - 44, pw, ph, PANEL)
        o.rect(x - 26, y0 - 44, 4, ph, GOLD)
        o.text("TABLE SKINS", x, y0 - 26, size=20, color=EMBER)
        rows = [("Deck", self.deck.name), ("Felt", self.felt.name)]
        for i, (label, val) in enumerate(rows):
            yy = y0 + 18 + i * 42
            sel = i == self.custom_row
            o.text(("> " if sel else "  ") + label, x, yy, size=18,
                   color=TEXT if sel else DIM)
            o.text(f"< {val} >" if sel else val, x + 150, yy, size=18,
                   color=GOLD if sel else DIM)
        # live deck preview: a face-up sample + the back
        card_render.draw_card(o, x + 300, y0 + 6, 66, 92, Card(1, "S"), self.deck)
        card_render.draw_card(o, x + 372, y0 + 6, 66, 92, None, self.deck,
                              face_up=False)
        o.text("Up/Down: pick   Left/Right: change   Tab: close",
               x, y0 + 128, size=13, color=DIM)

    def _draw_win(self, o, W, H):
        o.rect(0, 0, W, H, (10, 8, 6, 150))
        o.text("YOU WIN", W / 2, H / 2 - 40, size=64, color=GOLD, center=True)
        o.text(f"cleared in {self.model.moves} moves", W / 2, H / 2 + 26,
               size=22, color=TEXT, center=True)
        o.text("N: new deal    Esc: leave", W / 2, H / 2 + 80, size=18,
               color=EMBER, center=True)

    def on_event(self, etype, data, renderer, audio, banner):
        if etype == "sol_draw":
            audio.play("menu_move")
        elif etype == "sol_move":
            audio.play("menu_select")
        elif etype == "sol_home":
            audio.play("powerup")
        elif etype == "sol_undo":
            audio.play("menu_move")
        elif etype == "sol_deal":
            audio.play("menu_select")
        elif etype == "sol_win":
            audio.play("win")
            banner("YOU WIN!", 3.0)


def _in(px, py, x, y, w, h):
    return x <= px < x + w and y <= py < y + h


def create_run(mode, rng):
    return SolitaireRun(mode, rng)
