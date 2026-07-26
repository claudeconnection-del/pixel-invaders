"""Video Poker — the cabinet-side game module (TABLETOP category). 5-card
draw, full-pay 9/6 Jacks or Better. Rules + paytable + credits ledger in
games/poker/model.py; this is the table view, reusing the shared card
render + felt/skin plumbing (games/cards/table), modeled on games/rummy/game.py.

Set your bet (Left/Right, or M for max), D to deal. Toggle holds with the
number keys 1-5 or by clicking a card, then D again to draw. R rebuys 200
credits when you're tapped out.

Gamepad (CAB-23, not yet wired): adopt `table.PadCursor` like Solitaire/Rummy
— add a `pad_targets()` method (bet/deal button + one target per hand card),
`self.pad_cursor = table.PadCursor(self)` in `__init__`, `pad_cursor.draw(o)`
in `draw_hud`; the shared cursor's `confirm()` dispatches this module's own
`_click` at the target center, so no other change is needed.
"""
import pygame

from arcade.game_api import GameInfo, GameRun
from game.theme import TEXT, DIM, EMBER, GOLD, GOOD, PANEL
from games.cards import render as card_render
from games.cards import skins
from games.cards import table
from games.poker.achievements import ACHIEVEMENTS as _POKER_ACHIEVEMENTS
from games.poker.model import MAX_BET, PAYTABLE, RANK_ORDER, LABELS, VideoPoker

INFO = GameInfo(
    "poker", "VIDEO POKER",
    "Jacks or better — hold, draw, and let it ride.",
    showcase_sprite="cube",
    modes=[("jacks", "JACKS OR BETTER")],
    has_scores=False, attract=False, game_music=True, music_pool="menu",
)
ACHIEVEMENTS = _POKER_ACHIEVEMENTS
_GRIND_KEYS = ("vp_credits", "vp_rebuys", "vp_hands", "vp_paid",
               "vp_full_houses", "vp_best_credits")

STATS_ROWS = [
    ("Hands played", "vp_hands"),
    ("Paying hands", "vp_paid"),
    ("Full houses", "vp_full_houses"),
    ("Best credits", "vp_best_credits"),
    ("Credits", "vp_credits"),
    ("Rebuys", "vp_rebuys"),
]

RULES_TEXT = [
    "OBJECTIVE",
    "Draw a paying poker hand — Jacks or Better pays out.",
    "",
    "PLAY",
    "Set your bet (1-5), then DEAL five cards.",
    "Click cards (or 1-5) to HOLD the ones you keep, then DRAW.",
    "Un-held cards are replaced; the final hand is paid.",
    "",
    "PAYTABLE (per coin bet)",
    "Royal Flush 250   Straight Flush 50   Four of a Kind 25",
    "Full House 9   Flush 6   Straight 4   Three of a Kind 3",
    "Two Pair 2   Jacks or Better 1",
    "Max bet (5) royal flush pays the 4000 jackpot.",
    "",
    "CONTROLS",
    "Left/Right: bet   M: max   D: deal/draw   1-5/click: hold",
    "R: rebuy   Tab: skins   H: rules",
]

CARD_W, CARD_H = 90, 126
GAP = 20
REBUY_AMOUNT = 200
_PAYTABLE_ROWS = list(reversed(RANK_ORDER))[:-1]     # strongest first, no "nothing"


class VideoPokerRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode or "jacks"
        self.rng = rng
        self.model = VideoPoker(credits=REBUY_AMOUNT, bet=1)
        self.time = 0.0
        self.events = []
        self.section = None
        self.settings = None
        self.save_cb = lambda: None

        self.deck = skins.deck_by_id("classic")
        self.felt = skins.felt_by_id("emberlight")
        self.four_color = False                # accessibility: 4-color suit inks
        self._felt_preset = table.make_felt_preset(self.felt)
        self.picker = table.SkinPicker(self)
        self.rules = table.RulesOverlay(self)
        self.rules_title = INFO.name

        self.message = "Set your bet and DEAL."
        self._prev_mb = False
        self._W, self._H = 1280, 860
        self._hand_layout = []     # [(x, y)] per card slot, for hit-testing

    # ------------------------------------------------------ cabinet contract
    @property
    def score(self):
        return self.model.credits

    @property
    def run_over(self):
        return False

    def attach_profile(self, section, settings, save_cb):
        self.section = section
        self.settings = settings
        self.save_cb = save_cb
        tt = table.tabletop_store(settings)
        self.deck = skins.deck_by_id(tt.get("deck", "classic"))
        self._set_felt(skins.felt_by_id(tt.get("felt", "emberlight")))
        self.four_color = tt.get("four_color", False)
        life = section["lifetime"]
        life.setdefault("vp_credits", REBUY_AMOUNT)
        for k in _GRIND_KEYS:
            if k != "vp_credits":
                life.setdefault(k, 0)
        self.model.credits = life["vp_credits"]
        life["vp_best_credits"] = max(life["vp_best_credits"], self.model.credits)
        self._sync_unlocks()
        self.save_cb()

    def _sync_unlocks(self):
        """Mirror any earned cosmetic-unlock achievements into the shared
        tabletop store so the tied premium deck/felt becomes selectable."""
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
        return {}

    def run_summary(self):
        return {"win": False}

    # --------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        self._sync_unlocks()                # grant cosmetics as achievements land
        mb = pygame.mouse.get_pressed()[0] if pygame.get_init() else False
        if not self.picker.open and not self.rules.open and mb and not self._prev_mb:
            self._click(inp.aim_x, inp.aim_y)
        self._prev_mb = mb

    def rules_lines(self):
        return RULES_TEXT

    def _save_credits(self):
        if self.section is not None:
            life = self.section["lifetime"]
            life["vp_credits"] = self.model.credits
            life["vp_best_credits"] = max(life["vp_best_credits"], self.model.credits)
            self.save_cb()

    # ---------------------------------------------------------------- input
    def handle_key(self, key):
        if key == pygame.K_h:
            self.picker.open = False
            self.rules.toggle()
            return True
        if self.rules.open:
            self.rules.handle_key(key)
            return True
        if self.picker.open:
            self.picker.handle_key(key)
            return True
        if key == pygame.K_TAB:
            self.picker.toggle()
        elif key in (pygame.K_d, pygame.K_RETURN):
            self._deal_or_draw()
        elif key in (pygame.K_LEFT, pygame.K_MINUS):
            self._adjust_bet(-1)
        elif key in (pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS):
            self._adjust_bet(1)
        elif key == pygame.K_m:
            self._set_bet(MAX_BET)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
            self._toggle_hold(key - pygame.K_1)
        elif key == pygame.K_r:
            self._rebuy()
        return True

    def _adjust_bet(self, delta):
        if self.model.phase == "hold":
            return
        self._set_bet(self.model.bet + delta)

    def _set_bet(self, value):
        if self.model.phase == "hold":
            return
        self.model.bet = max(1, min(MAX_BET, value))

    def _toggle_hold(self, i):
        if self.model.toggle_hold(i):
            self.emit("vp_hold")

    def _rebuy(self):
        if self.model.phase == "hold" or self.model.credits >= self.model.bet:
            return
        self.model.credits += REBUY_AMOUNT
        if self.section is not None:
            life = self.section["lifetime"]
            life["vp_rebuys"] = life.get("vp_rebuys", 0) + 1
        self._save_credits()
        self.message = f"Rebought {REBUY_AMOUNT} credits."
        self.emit("vp_rebuy")

    def _deal_or_draw(self):
        m = self.model
        if m.phase == "hold":
            rank_key, label, won = m.draw()
            self._save_credits()
            if self.section is not None:
                life = self.section["lifetime"]
                if won > 0:
                    life["vp_paid"] = life.get("vp_paid", 0) + 1
                if rank_key == "full_house":
                    life["vp_full_houses"] = life.get("vp_full_houses", 0) + 1
                self.save_cb()
            if won > 0:
                self.message = f"{label.upper()} — +{won}"
                self.emit("vp_win", rank_key=rank_key, amount=won)
            else:
                self.message = "No win. D: deal again."
                self.emit("vp_lose")
            return
        if m.credits < m.bet:
            self.message = "Not enough credits — R to rebuy."
            return
        if m.deal(self.rng):
            self._save_credits()
            if self.section is not None:
                life = self.section["lifetime"]
                life["vp_hands"] = life.get("vp_hands", 0) + 1
                self.save_cb()
            self.emit("vp_deal")
            self.message = "Toggle holds (1-5), then D to draw."

    def _click(self, px, py):
        if self.model.phase == "hold":
            for i, (x, y) in enumerate(self._hand_layout):
                if x <= px < x + CARD_W and y <= py < y + CARD_H:
                    self._toggle_hold(i)
                    return
        if _in(px, py, *self._deal_rect()):
            self._deal_or_draw()
        elif _in(px, py, *self._rebuy_rect()):
            self._rebuy()
        elif _in(px, py, *self._bet_rect(-1)):
            self._adjust_bet(-1)
        elif _in(px, py, *self._bet_rect(1)):
            self._adjust_bet(1)

    # ------------------------------------------------------------ layout
    def _ox(self):
        return self._W / 2

    def _hand_y(self):
        return self._H / 2 - CARD_H / 2

    def _deal_rect(self):
        return (self._ox() - 70, self._hand_y() + CARD_H + 40, 140, 44)

    def _rebuy_rect(self):
        return (self._ox() - 70, self._hand_y() + CARD_H + 96, 140, 36)

    def _bet_rect(self, direction):
        y = self._hand_y() - 56
        return (self._ox() - 90, y, 30, 30) if direction < 0 else \
            (self._ox() + 60, y, 30, 30)

    # ------------------------------------------------------------ drawing
    def draw(self, renderer, section):
        self._W, self._H = renderer.ui_w, renderer.ui_h
        table.draw_felt_backdrop(renderer, self.felt, self._felt_preset, self.time)

    def draw_hud(self, o, width, height, section):
        o.offset_x = 0.0
        W, H = self._W, self._H
        table.draw_felt_wash(o, W, H, self.felt)
        m = self.model

        o.text(f"CREDITS {m.credits}", 28, 26, size=20, color=EMBER)
        o.text(self.message, W / 2, 28, size=17, color=TEXT, center=True)

        self._draw_paytable(o)
        self._draw_bet(o)
        self._draw_hand(o)
        self._draw_buttons(o)

        o.text("Click/1-5: hold   D: deal/draw   Left/Right: bet   "
               "M: max bet   R: rebuy   Tab: skins   H: rules",
               W / 2, H - 32, size=13, color=DIM, center=True)
        if self.picker.open:
            self.picker.draw(o)
        if self.rules.open:
            self.rules.draw(o, W, H)

    def _draw_paytable(self, o):
        m = self.model
        x, y0 = 30, 140
        winning = m.last_result[0] if m.phase == "paid" and m.last_result else None
        o.text("PAYTABLE", x, y0 - 24, size=16, color=GOLD)
        for i, key in enumerate(_PAYTABLE_ROWS):
            y = y0 + i * 26
            won_row = key == winning
            payout = m.bet * PAYTABLE[key]
            if key == "royal_flush" and m.bet == MAX_BET:
                from games.poker.model import ROYAL_MAX_BET_JACKPOT
                payout = ROYAL_MAX_BET_JACKPOT
            color = GOLD if won_row else (TEXT if key != "nothing" else DIM)
            o.text(LABELS[key], x, y, size=14, color=color)
            o.text(str(payout), x + 190, y, size=14, color=color)

    def _draw_bet(self, o):
        m = self.model
        y = self._hand_y() - 56
        lx, ly, lw, lh = self._bet_rect(-1)
        rx, ry, rw, rh = self._bet_rect(1)
        o.rect(lx, ly, lw, lh, PANEL)
        o.text("-", lx + lw / 2, ly + 4, size=20, color=TEXT, center=True)
        o.text(f"BET {m.bet}", self._ox(), y + 4, size=20, color=EMBER, center=True)
        o.rect(rx, ry, rw, rh, PANEL)
        o.text("+", rx + rw / 2, ry + 4, size=20, color=TEXT, center=True)

    def _draw_hand(self, o):
        m = self.model
        n = len(m.hand) if m.hand else 5
        total = n * CARD_W + (n - 1) * GAP
        x0 = self._ox() - total / 2
        y = self._hand_y()
        self._hand_layout = []
        for i in range(5):
            x = x0 + i * (CARD_W + GAP)
            self._hand_layout.append((x, y))
            card = m.hand[i] if m.hand else None
            held = m.phase == "hold" and m.held[i]
            card_render.draw_card(o, x, y, CARD_W, CARD_H, card, self.deck,
                                  face_up=bool(m.hand), selected=held,
                                  four_color=self.four_color)
            if held:
                o.text("HELD", x + CARD_W / 2, y - 20, size=13, color=GOLD,
                       center=True)

    def _draw_buttons(self, o):
        m = self.model
        dx, dy, dw, dh = self._deal_rect()
        label = "DRAW" if m.phase == "hold" else "DEAL"
        o.rect(dx, dy, dw, dh, PANEL)
        o.rect(dx, dy, dw, 3, GOLD)
        o.text(label, dx + dw / 2, dy + 12, size=20, color=GOLD, center=True)
        if m.phase != "hold" and m.credits < m.bet:
            rx, ry, rw, rh = self._rebuy_rect()
            o.rect(rx, ry, rw, rh, PANEL)
            o.text(f"REBUY {REBUY_AMOUNT}", rx + rw / 2, ry + 8, size=15,
                   color=GOOD, center=True)

    def on_event(self, etype, data, renderer, audio, banner):
        if etype == "vp_deal":
            audio.play("card_shuffle")
        elif etype == "vp_hold":
            audio.play("card_flip")
        elif etype == "vp_rebuy":
            audio.play("chip_stack")
        elif etype == "vp_win":
            audio.play("chip_stack")            # credits land on the felt
            audio.play("win" if data["amount"] >= 100 else "powerup")
            banner(f"+{data['amount']}", 1.6)
        elif etype == "vp_lose":
            audio.play("card_flip")             # the draw flips, no payout


def _in(px, py, x, y, w, h):
    return x <= px < x + w and y <= py < y + h


def create_run(mode, rng):
    return VideoPokerRun(mode, rng)
