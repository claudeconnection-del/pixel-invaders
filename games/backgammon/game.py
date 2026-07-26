"""Backgammon — the cabinet-side game module (TABLETOP category). You (A)
play the house (B) — standard direction/home-board rules in
games/backgammon/model.py; this is the table view, reusing the shared felt +
skin plumbing (games/cards/table) like the card games, plus its own BoardSkin
cosmetic (board/checker colors — a board isn't cards, so it isn't a deck).

Turn: R (or click ROLL) rolls the dice. Click a highlighted source point (or
the bar, if you have a checker on it), then a highlighted destination (or the
OFF tray once you're bearing off) to play one die; repeat until the roll is
used up — the turn then commits automatically. U undoes the turn's picks so
far (back to the roll) if you change your mind mid-turn. The house plays
itself with a short beat, same cadence as Gin Rummy.
"""
import random

import pygame

from arcade.game_api import GameInfo, GameRun
from game.theme import TEXT, DIM, EMBER, GOLD, GOOD, DANGER, PANEL
from games.backgammon.achievements import ACHIEVEMENTS as _BG_ACHIEVEMENTS
from games.backgammon.ai import ai_move
from games.backgammon.model import Backgammon, simulate
from games.cards import skins
from games.cards import table

INFO = GameInfo(
    "backgammon", "BACKGAMMON",
    "Roll, run, and bear off against the house.",
    showcase_sprite="cube",
    modes=[("standard", "BACKGAMMON")],
    has_scores=False, attract=False, game_music=True, music_pool="menu",
)
ACHIEVEMENTS = _BG_ACHIEVEMENTS
_GRIND_KEYS = ("bg_games", "bg_wins", "bg_gammons", "bg_backgammons")

HUMAN, HOUSE = "A", "B"

BOARD_W, BOARD_H = 900, 460
BAR_W = 46
POINT_H = 175
COL_W = (BOARD_W - BAR_W) / 12
CHECKER = min(COL_W - 10, 34)

# slot (0-11, left->right within a row) -> board point index
_BOTTOM_ORDER = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
_TOP_ORDER = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
_POINT_ROW_SLOT = {}
for _slot, _idx in enumerate(_BOTTOM_ORDER):
    _POINT_ROW_SLOT[_idx] = ("bottom", _slot)
for _slot, _idx in enumerate(_TOP_ORDER):
    _POINT_ROW_SLOT[_idx] = ("top", _slot)

_SEL = (255, 210, 90, 230)


class BackgammonRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode or "standard"
        self.rng = rng
        self.model = Backgammon(rng)
        self.time = 0.0
        self.events = []
        self.section = None
        self.settings = None
        self.save_cb = lambda: None

        self.board = skins.board_by_id("emberlight_walnut")
        self.felt = skins.felt_by_id("emberlight")
        self._felt_preset = table.make_felt_preset(self.felt)
        self.picker = table.SkinPicker(self)

        self.legal_seqs = []      # all maximal legal sequences for this roll
        self.chosen = []          # moves picked so far this turn
        self.sel_from = None      # currently selected source (index, "bar", or None)
        self.message = "Your turn — R to roll."
        self._ai_timer = 0.0
        self._prev_mb = False
        self._max_pip_deficit = 0   # for the "pip_race" comeback achievement
        self._W, self._H = 1280, 860

    def picker_rows(self):
        """No deck here (a board isn't cards) — Board + Felt instead."""
        return (("Board", "board"), ("Felt", "felt"))

    # ------------------------------------------------------ cabinet contract
    @property
    def score(self):
        return self.model.off[HUMAN]

    @property
    def run_over(self):
        return False

    def attach_profile(self, section, settings, save_cb):
        self.section = section
        self.settings = settings
        self.save_cb = save_cb
        tt = table.tabletop_store(settings)
        self.board = skins.board_by_id(tt.get("board", "emberlight_walnut"))
        self._set_felt(skins.felt_by_id(tt.get("felt", "emberlight")))
        life = section["lifetime"]
        for k in _GRIND_KEYS:
            life.setdefault(k, 0)
        life["bg_games"] += 1        # this freshly-started game counts as played
        self._sync_unlocks()
        self.save_cb()

    def _sync_unlocks(self):
        table.sync_unlocks(self.section, self.settings, self.save_cb)

    def _set_felt(self, felt):
        self.felt = felt
        self._felt_preset = table.make_felt_preset(felt)

    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out, self.events = self.events, []
        return out

    def run_stats(self):
        return {"max_pip_deficit": self._max_pip_deficit}

    def run_summary(self):
        return {"win": False}

    # --------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        self._sync_unlocks()
        if self.model.winner is None:
            deficit = self.model.pip_count(HUMAN) - self.model.pip_count(HOUSE)
            self._max_pip_deficit = max(self._max_pip_deficit, deficit)
        if self.model.turn == HOUSE and self.model.winner is None:
            self._ai_timer += dt
            if self._ai_timer >= 0.8:
                self._ai_timer = 0.0
                self._house_turn()
        mb = pygame.mouse.get_pressed()[0] if pygame.get_init() else False
        if not self.picker.open and mb and not self._prev_mb:
            self._click(inp.aim_x, inp.aim_y)
        self._prev_mb = mb

    def _house_turn(self):
        m = self.model
        if not m.dice:
            m.roll()
            self.emit("bg_roll")
            self.message = "House rolls " + " ".join(str(d) for d in m.dice)
            return
        seq = ai_move(m)
        if any(mv.get("hit") for mv in seq):
            self.emit("bg_hit")
        self.emit("bg_move")
        if m.winner:
            self._announce_result()
        else:
            self.message = "Your turn — R to roll."

    def _announce_result(self):
        r = self.model.result
        won = r["winner"] == HUMAN
        grade = r["grade"]
        tag = {"single": "", "gammon": "GAMMON! ", "backgammon": "BACKGAMMON! "}[grade]
        who = "You win" if won else "The house wins"
        self.message = f"{tag}{who} ({grade}). N: rematch."
        if won and self.section is not None:
            life = self.section["lifetime"]
            life["bg_wins"] = life.get("bg_wins", 0) + 1
            if grade == "gammon":
                life["bg_gammons"] = life.get("bg_gammons", 0) + 1
            elif grade == "backgammon":
                life["bg_backgammons"] = life.get("bg_backgammons", 0) + 1
            self.save_cb()
        self.emit("bg_win" if won else "bg_lose", grade=grade)

    # ---------------------------------------------------------------- input
    def handle_key(self, key):
        if self.picker.open:
            self.picker.handle_key(key)
            return True
        if key == pygame.K_TAB:
            self.picker.toggle()
        elif key == pygame.K_r:
            self._roll()
        elif key == pygame.K_u:
            self._undo()
        elif key in (pygame.K_n, pygame.K_RETURN):
            if self.model.winner:
                self._new_game()
        return True

    def _roll(self):
        m = self.model
        if m.turn != HUMAN or m.dice or m.winner:
            return
        m.roll()
        self.legal_seqs = m.legal_moves(HUMAN, m.dice)
        self.chosen = []
        self.sel_from = None
        self.emit("bg_roll")
        if max(len(s) for s in self.legal_seqs) == 0:
            self.message = "No legal moves — turn passes."
            m.dice = []
            m.turn = HOUSE
        else:
            self.message = "Move your checkers (U: undo the roll)."

    def _undo(self):
        if self.model.turn == HUMAN and self.model.dice and self.chosen:
            self.chosen = []
            self.sel_from = None
            self.message = "Move your checkers (U: undo the roll)."

    def _new_game(self):
        self.model = Backgammon(random.Random())
        self.legal_seqs = []
        self.chosen = []
        self.sel_from = None
        self._max_pip_deficit = 0
        self.message = "Your turn — R to roll."
        if self.section is not None:
            self.section["lifetime"]["bg_games"] += 1
            self.save_cb()

    def _legal_next_moves(self):
        """Move-dicts legal as the *next* atomic move given self.chosen."""
        n = len(self.chosen)
        seen = {}
        for s in self.legal_seqs:
            if len(s) > n and s[:n] == tuple(self.chosen):
                mv = s[n]
                seen[(mv["from"], mv["to"])] = mv
        return list(seen.values())

    def _click(self, px, py):
        m = self.model
        if m.turn != HUMAN or not m.dice or m.winner:
            return
        hit = self._hit_point(px, py)
        if hit is None and self._in_off_tray(px, py):
            hit = "off"
        legal_next = self._legal_next_moves()
        if self.sel_from is None:
            sources = {mv["from"] for mv in legal_next}
            if hit in sources:
                self.sel_from = hit
            return
        for mv in legal_next:
            if mv["from"] == self.sel_from and mv["to"] == hit:
                self.chosen.append(mv)
                self.sel_from = None
                self.emit("bg_move")
                self._maybe_commit()
                return
        sources = {mv["from"] for mv in legal_next}
        self.sel_from = hit if hit in sources else None

    def _maybe_commit(self):
        max_len = max(len(s) for s in self.legal_seqs)
        if len(self.chosen) >= max_len:
            seq = tuple(self.chosen)
            hit_any = any(mv.get("hit") for mv in seq)
            self.model.apply(seq)
            if hit_any:
                self.emit("bg_hit")
            self.chosen = []
            self.legal_seqs = []
            if self.model.winner:
                self._announce_result()
            else:
                self.message = "House's turn…"

    # ------------------------------------------------------------ layout
    def _ox(self):
        return self._W / 2 - BOARD_W / 2

    def _oy(self):
        return self._H / 2 - BOARD_H / 2 - 10

    def _slot_x(self, slot):
        if slot < 6:
            return self._ox() + slot * COL_W
        return self._ox() + 6 * COL_W + BAR_W + (slot - 6) * COL_W

    def _point_rect(self, i):
        row, slot = _POINT_ROW_SLOT[i]
        x = self._slot_x(slot)
        y = self._oy() if row == "top" else self._oy() + BOARD_H - POINT_H
        return x, y, COL_W, POINT_H

    def _bar_rect(self):
        return self._ox() + 6 * COL_W, self._oy(), BAR_W, BOARD_H

    def _off_rect(self, player):
        x = self._ox() + BOARD_W + 14
        y = self._oy() if player == HOUSE else self._oy() + BOARD_H - 90
        return x, y, 70, 90

    def _roll_rect(self):
        return self._ox() + BOARD_W / 2 - 70, self._oy() - 56, 140, 40

    def _hit_point(self, px, py):
        bx, by, bw, bh = self._bar_rect()
        if bx <= px < bx + bw and by <= py < by + bh:
            return "bar"
        for i in range(24):
            x, y, w, h = self._point_rect(i)
            if x <= px < x + w and y <= py < y + h:
                return i
        return None

    def _in_off_tray(self, px, py):
        for player in (HUMAN, HOUSE):
            x, y, w, h = self._off_rect(player)
            if x <= px < x + w and y <= py < y + h:
                return True
        return False

    # ------------------------------------------------------------ drawing
    def _preview_state(self):
        m = self.model
        if self.chosen:
            return simulate(m.points, m.bar, m.off, HUMAN, self.chosen)
        return m.points, m.bar, m.off

    def draw(self, renderer, section):
        self._W, self._H = renderer.ui_w, renderer.ui_h
        table.draw_felt_backdrop(renderer, self.felt, self._felt_preset, self.time)

    def draw_hud(self, o, width, height, section):
        o.offset_x = 0.0
        W, H = self._W, self._H
        table.draw_felt_wash(o, W, H, self.felt)
        m = self.model
        pts, bar, off = self._preview_state()

        o.text(f"YOU {m.pip_count(HUMAN)} pips  ·  off {off[HUMAN]}/15",
               28, 26, size=17, color=EMBER)
        o.text(f"HOUSE {m.pip_count(HOUSE)} pips  ·  off {off[HOUSE]}/15",
               28, 50, size=15, color=DIM)
        o.text(self.message, W / 2, 26, size=16, color=TEXT, center=True)

        legal_next = self._legal_next_moves() if (m.turn == HUMAN and m.dice) else []
        sources = {mv["from"] for mv in legal_next}
        dests = ({mv["to"] for mv in legal_next if mv["from"] == self.sel_from}
                 if self.sel_from is not None else set())

        for i in range(24):
            x, y, w, h = self._point_rect(i)
            row, _ = _POINT_ROW_SLOT[i]
            self._draw_point(o, i, x, y, w, h, row == "top")
            if i in sources or i in dests:
                o.rect(x + 2, y + h - 6, w - 4, 4, _SEL)
            self._draw_checkers(o, x, y, w, h, row == "top", pts[i])

        self._draw_bar(o, bar, sources, dests)
        self._draw_off(o, off, dests)
        self._draw_dice(o)
        self._draw_roll_button(o)

        o.text("Click: pick/place   U: undo roll   N: rematch   Tab: skins",
               W / 2, H - 32, size=13, color=DIM, center=True)
        if m.winner:
            self._draw_result(o, W, H)
        if self.picker.open:
            self.picker.draw(o)

    def _draw_point(self, o, i, x, y, w, h, top_row):
        color = (*self.board.point_light, 255) if i % 2 == 0 \
            else (*self.board.point_dark, 255)
        segs = 5
        for s in range(segs):
            seg_w = w * (1 - (s + 0.5) / segs)
            seg_x = x + (w - seg_w) / 2
            seg_h = h / segs + 1
            seg_y = y + s * (h / segs) if top_row else y + h - (s + 1) * (h / segs)
            o.rect(seg_x, seg_y, seg_w, seg_h, color)

    def _draw_checkers(self, o, x, y, w, h, top_row, n):
        if n == 0:
            return
        player = HUMAN if n > 0 else HOUSE
        count = abs(n)
        color = (*self.board.checker_a, 255) if player == HUMAN \
            else (*self.board.checker_b, 255)
        edge = (*self.board.checker_trim, 255)
        size = CHECKER
        cx = x + w / 2
        shown = min(count, 5)
        for k in range(shown):
            cy = (y + 6 + k * (size + 4)) if top_row else (y + h - 6 - (k + 1) * (size + 4))
            o.rect(cx - size / 2, cy, size, size, color)
            o.rect(cx - size / 2, cy, size, 3, edge)
        if count > 5:
            label_y = (y + 10 + shown * (size + 4)) if top_row \
                else (y + h - 10 - (shown + 1) * (size + 4))
            o.text(f"+{count - 5}", cx, label_y, size=13, color=TEXT, center=True)

    def _draw_bar(self, o, bar, sources, dests):
        x, y, w, h = self._bar_rect()
        o.rect(x, y, w, h, (18, 14, 10, 230))
        sel = "bar" in sources or "bar" in dests
        if sel:
            o.rect(x + 2, y + h / 2 - 2, w - 4, 4, _SEL)
        if bar[HOUSE]:
            o.rect(x + 6, y + 8, w - 12, CHECKER, (*self.board.checker_b, 255))
            o.text(str(bar[HOUSE]), x + w / 2, y + 8 + CHECKER / 2 - 8, size=14,
                   color=TEXT, center=True)
        if bar[HUMAN]:
            o.rect(x + 6, y + h - 8 - CHECKER, w - 12, CHECKER,
                   (*self.board.checker_a, 255))
            o.text(str(bar[HUMAN]), x + w / 2, y + h - 8 - CHECKER / 2 - 8, size=14,
                   color=TEXT, center=True)

    def _draw_off(self, o, off, dests):
        for player in (HUMAN, HOUSE):
            x, y, w, h = self._off_rect(player)
            o.rect(x, y, w, h, PANEL)
            if "off" in dests and player == HUMAN:
                o.rect(x, y, w, 4, _SEL)
            label = "YOU" if player == HUMAN else "HOUSE"
            o.text(f"{label} OFF", x + w / 2, y + 8, size=12, color=DIM, center=True)
            o.text(str(off[player]), x + w / 2, y + h / 2, size=24,
                   color=GOOD, center=True)

    def _draw_dice(self, o):
        m = self.model
        if not m.dice or m.winner:
            return
        shown = sorted(set(m.dice)) if len(m.dice) == 4 else m.dice
        x0 = self._ox() + BOARD_W / 2 - (len(shown) * 44) / 2
        y = self._oy() - 56
        for i, d in enumerate(shown):
            x = x0 + i * 44
            o.rect(x, y, 36, 36, PANEL)
            o.rect(x, y, 36, 3, GOLD)
            o.text(str(d), x + 18, y + 8, size=20, color=GOLD, center=True)

    def _draw_roll_button(self, o):
        m = self.model
        if m.turn != HUMAN or m.dice or m.winner:
            return
        x, y, w, h = self._roll_rect()
        o.rect(x, y, w, h, PANEL)
        o.rect(x, y, w, 3, GOLD)
        o.text("ROLL", x + w / 2, y + 10, size=20, color=GOLD, center=True)

    def _draw_result(self, o, W, H):
        r = self.model.result
        o.rect(0, H / 2 - 110, W, 220, (10, 8, 6, 170))
        won = r["winner"] == HUMAN
        head = {"single": "", "gammon": "GAMMON ", "backgammon": "BACKGAMMON "}[r["grade"]]
        o.text(head + ("YOU WIN" if won else "HOUSE WINS"), W / 2, H / 2 - 30,
               size=44, color=GOLD if won else DANGER, center=True)
        o.text("N: rematch    Esc: leave", W / 2, H / 2 + 40, size=18,
               color=EMBER, center=True)

    def on_event(self, etype, data, renderer, audio, banner):
        if etype == "bg_roll":
            audio.play("menu_move")
        elif etype == "bg_move":
            audio.play("menu_select")
        elif etype == "bg_hit":
            audio.play("powerup")
        elif etype == "bg_win":
            grade = data.get("grade", "single")
            banner(("GAMMON! " if grade == "gammon" else
                    "BACKGAMMON! " if grade == "backgammon" else "") + "YOU WIN", 2.5)
            audio.play("win")
        elif etype == "bg_lose":
            audio.play("game_over")


def create_run(mode, rng):
    return BackgammonRun(mode, rng)
