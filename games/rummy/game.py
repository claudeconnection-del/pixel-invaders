"""Gin Rummy — the cabinet-side game module (TABLETOP category). You (P1) play
the bottom hand face-up against the house AI (P2) up top. Rules + meld engine in
games/rummy/model.py; this is the table view, reusing the shared card render +
felt/skin plumbing (games/cards/table).

Turn: on your turn, click the stock (blind) or the discard pile (take the up
card) to draw, then click a card in your hand to discard. KNOCK when your
deadwood would be 10 or less. The house plays itself with a short beat.
"""
import random

import pygame

from arcade.game_api import GameInfo, GameRun
from game.theme import TEXT, DIM, EMBER, GOLD, GOOD, DANGER, PANEL
from games.cards import render as card_render
from games.cards import skins
from games.cards import table
from games.rummy.model import GinRummy, best_deadwood, deadwood, deadwood_value

INFO = GameInfo(
    "rummy", "GIN RUMMY",
    "Meld, knock, and gin against the house.",
    showcase_sprite="cube",
    modes=[("gin", "GIN RUMMY")],
    has_scores=False, attract=False, game_music=True, music_pool="menu",
)
ACHIEVEMENTS = []          # wired in a later increment

CARD_W, CARD_H = 90, 126
FAN = 74                   # hand fan spacing
GROUP_GAP = 22             # gap between melds / the deadwood group
HUMAN, HOUSE = "P1", "P2"


class GinRummyRun(GameRun):
    def __init__(self, mode, rng):
        self.mode = mode or "gin"
        self.rng = rng
        self.model = GinRummy(rng, target=100)
        self.time = 0.0
        self.events = []
        self.section = None
        self.settings = None
        self.save_cb = lambda: None

        self.deck = skins.deck_by_id("classic")
        self.felt = skins.felt_by_id("emberlight")
        self._felt_preset = table.make_felt_preset(self.felt)
        self.picker = table.SkinPicker(self)

        self.knock_mode = False
        self.message = "Your turn — draw from the stock or the discard."
        self._ai_timer = 0.0
        self._prev_mb = False
        self._W, self._H = 1280, 860
        self._hand_layout = []     # [(card, x, melded)] for hit-testing
        self._first = HUMAN

    # ------------------------------------------------------ cabinet contract
    @property
    def score(self):
        return self.model.scores[HUMAN]

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
        return {"win": self.model.scores[HUMAN] >= self.model.target}

    # --------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        if self.model.turn == HOUSE and not self.model.hand_over \
                and not self.model.game_over:
            self._ai_timer += dt
            if self._ai_timer >= 0.8:
                self._ai_timer = 0.0
                self._house_turn()
        mb = pygame.mouse.get_pressed()[0] if pygame.get_init() else False
        if not self.picker.open and mb and not self._prev_mb:
            self._click(inp.aim_x, inp.aim_y)
        self._prev_mb = mb

    def _house_turn(self):
        from games.rummy.ai import ai_turn
        res = ai_turn(self.model)
        if res.get("washed"):
            self.message = "Stock ran out — hand washed. N: deal again."
            self.emit("rm_deal")
            return
        self.emit("rm_discard")
        if res.get("knock"):
            self._announce()
        else:
            self.message = "Your turn — draw a card."

    def _announce(self):
        r = self.model.result
        if r.get("washed"):
            self.message = "Hand washed. N: deal again."
            return
        who = "You" if r["winner"] == HUMAN else "The house"
        tag = "GIN! " if r["gin"] else ""
        self.message = (f"{tag}{who} {'win' if who == 'You' else 'wins'} the hand "
                        f"(+{r['points']}). N: next hand.")
        self.emit("rm_win" if r["winner"] == HUMAN else "rm_lose")

    # ---------------------------------------------------------------- input
    def handle_key(self, key):
        if self.picker.open:
            self.picker.handle_key(key)
            return True
        if key == pygame.K_TAB:
            self.picker.toggle()
        elif key in (pygame.K_n, pygame.K_RETURN):
            if self.model.game_over:
                self.model = GinRummy(random.Random(), target=100)
                self._first = HUMAN
                self.message = "New game. Your turn."
            elif self.model.hand_over:
                self._first = HOUSE if self._first == HUMAN else HUMAN
                self.model.deal(first=self._first)
                self.knock_mode = False
                self.message = ("Your turn." if self._first == HUMAN
                                else "House to start.")
        elif key == pygame.K_k:
            self._toggle_knock()
        return True

    def _toggle_knock(self):
        if self.model.turn == HUMAN and self.model.phase == "discard":
            self.knock_mode = not self.knock_mode
            self.message = ("Knock armed — discard a card to end the hand."
                            if self.knock_mode else "Your turn — discard a card.")

    def _click(self, px, py):
        m = self.model
        if m.hand_over or m.game_over or m.turn != HUMAN:
            return
        if m.phase == "draw":
            if _in(px, py, *self._stock_rect()):
                if m.draw("stock"):
                    self.emit("rm_draw")
                    self.message = "Discard a card." + self._knock_hint()
            elif m.discard and _in(px, py, *self._discard_rect()):
                m.draw("discard")
                self.emit("rm_draw")
                self.message = "Discard a card." + self._knock_hint()
            return
        # discard phase
        if _in(px, py, *self._knock_rect()) and self._knock_available():
            self._toggle_knock()
            return
        card = self._hand_hit(px, py)
        if card is not None:
            if m.discard_card(card, knock=self.knock_mode):
                self.emit("rm_discard")
                self.knock_mode = False
                if m.hand_over:
                    self._announce()
                else:
                    self.message = "House's turn…"
            elif self.knock_mode:
                self.message = "Deadwood too high to knock with that discard."

    def _knock_hint(self):
        return "  (K: knock)" if self._knock_available() else ""

    def _knock_available(self):
        """True if some discard leaves the hand knockable (<= 10 deadwood)."""
        hand = self.model.hands[HUMAN]
        if len(hand) < 11:
            return False
        return any(deadwood([c for c in hand if c is not x]) <= 10 for x in hand)

    # ------------------------------------------------------------ layout
    def _ox(self):
        return self._W / 2

    def _stock_rect(self):
        return (self._ox() - CARD_W - 14, 300, CARD_W, CARD_H)

    def _discard_rect(self):
        return (self._ox() + 14, 300, CARD_W, CARD_H)

    def _knock_rect(self):
        return (self._ox() - 70, 470, 140, 40)

    def _human_layout(self):
        """[(card, x, melded)] left-to-right: melds grouped, then deadwood."""
        hand = self.model.hands[HUMAN]
        _, melds = best_deadwood(hand)
        melded = set()
        groups = []
        for meld in melds:
            groups.append(list(meld))
            melded.update(meld)
        loose = sorted((c for c in hand if c not in melded),
                       key=lambda c: (-deadwood_value(c.rank), c.suit))
        if loose:
            groups.append(loose)
        n = sum(len(g) for g in groups)
        total = n * FAN + max(0, len(groups) - 1) * GROUP_GAP
        x = self._ox() - total / 2
        out = []
        for gi, g in enumerate(groups):
            for c in g:
                out.append((c, x, c in melded))
                x += FAN
            x += GROUP_GAP
        return out

    def _hand_hit(self, px, py):
        if not (self._hand_y() <= py < self._hand_y() + CARD_H):
            return None
        hit = None
        for card, x, _ in self._hand_layout:      # last (rightmost) wins on overlap
            if x <= px < x + CARD_W:
                hit = card
        return hit

    def _hand_y(self):
        return self._H - CARD_H - 70

    # ------------------------------------------------------------ drawing
    def draw(self, renderer, section):
        self._W, self._H = renderer.ui_w, renderer.ui_h
        table.draw_felt_backdrop(renderer, self.felt, self._felt_preset, self.time)

    def draw_hud(self, o, width, height, section):
        o.offset_x = 0.0
        W, H = self._W, self._H
        table.draw_felt_wash(o, W, H, self.felt)
        m = self.model

        # scores + status
        o.text(f"YOU {m.scores[HUMAN]}", 28, 26, size=20, color=EMBER)
        o.text(f"HOUSE {m.scores[HOUSE]}", 28, 52, size=16, color=DIM)
        o.text(f"to {m.target}", 28, 74, size=12, color=DIM)
        o.text(self.message, W / 2, 28, size=17, color=TEXT, center=True)

        # house hand (face-down), centred at top
        self._draw_fan(o, m.hands[HOUSE], 66, face_up=False)

        # stock + discard
        sx, sy, sw, sh = self._stock_rect()
        if m.stock:
            card_render.draw_card(o, sx, sy, sw, sh, None, self.deck, face_up=False)
        else:
            card_render.draw_slot(o, sx, sy, sw, sh, "O")
        o.text("stock", sx + sw / 2, sy + sh + 4, size=12, color=DIM, center=True)
        dx, dy, dw, dh = self._discard_rect()
        if m.discard:
            card_render.draw_card(o, dx, dy, dw, dh, m.discard[-1], self.deck)
        else:
            card_render.draw_slot(o, dx, dy, dw, dh)
        o.text("discard", dx + dw / 2, dy + dh + 4, size=12, color=DIM, center=True)

        # your hand (face-up, melds grouped, deadwood dimmed)
        self._hand_layout = self._human_layout()
        hy = self._hand_y()
        for card, x, melded in self._hand_layout:
            card_render.draw_card(o, x, hy, CARD_W, CARD_H, card, self.deck)
            if melded:
                o.rect(x + 2, hy + CARD_H - 6, CARD_W - 4, 4, (*GOOD[:3], 220))
        dead = deadwood(m.hands[HUMAN])
        o.text(f"deadwood {dead}", W / 2, hy - 26, size=15,
               color=GOOD if dead <= 10 else DIM, center=True)

        # knock button (discard phase, when knockable)
        if m.turn == HUMAN and m.phase == "discard" and self._knock_available():
            kx, ky, kw, kh = self._knock_rect()
            on = self.knock_mode
            o.rect(kx, ky, kw, kh, (60, 44, 24, 230) if on else PANEL)
            o.rect(kx, ky, kw, 3, GOLD)
            o.text("KNOCK", kx + kw / 2, ky + 10, size=20,
                   color=GOLD if on else TEXT, center=True)

        o.text("Click: draw / discard   K: knock   N: deal   Tab: skins",
               W / 2, H - 32, size=13, color=DIM, center=True)

        if m.hand_over or m.game_over:
            self._draw_result(o, W, H)
        if self.picker.open:
            self.picker.draw(o)

    def _draw_fan(self, o, cards, y, face_up):
        n = len(cards)
        total = (n - 1) * FAN + CARD_W
        x = self._ox() - total / 2
        for c in cards:
            card_render.draw_card(o, x, y, CARD_W, CARD_H, c, self.deck,
                                  face_up=face_up)
            x += FAN

    def _draw_result(self, o, W, H):
        m = self.model
        o.rect(0, H / 2 - 150, W, 300, (10, 8, 6, 160))
        r = m.result or {}
        if m.game_over:
            you = m.scores[HUMAN] >= m.target
            o.text("YOU WIN THE GAME" if you else "THE HOUSE WINS",
                   W / 2, H / 2 - 30, size=48, color=GOLD if you else DANGER,
                   center=True)
            o.text(f"{m.scores[HUMAN]} — {m.scores[HOUSE]}", W / 2, H / 2 + 30,
                   size=24, color=TEXT, center=True)
            o.text("N: new game    Esc: leave", W / 2, H / 2 + 80, size=18,
                   color=EMBER, center=True)
        elif not r.get("washed"):
            you = r.get("winner") == HUMAN
            head = ("GIN! " if r.get("gin") else "") + \
                   ("You take the hand" if you else "The house takes the hand")
            o.text(head, W / 2, H / 2 - 20, size=34,
                   color=GOOD if you else DANGER, center=True)
            o.text(f"+{r.get('points', 0)}   ·   YOU {m.scores[HUMAN]}  "
                   f"HOUSE {m.scores[HOUSE]}", W / 2, H / 2 + 26, size=20,
                   color=TEXT, center=True)
            o.text("N: next hand", W / 2, H / 2 + 74, size=18, color=EMBER,
                   center=True)

    def on_event(self, etype, data, renderer, audio, banner):
        if etype in ("rm_draw", "rm_discard"):
            audio.play("menu_move")
        elif etype == "rm_deal":
            audio.play("menu_select")
        elif etype == "rm_win":
            audio.play("win")
            banner("HAND WON", 2.0)
        elif etype == "rm_lose":
            audio.play("game_over")


def _in(px, py, x, y, w, h):
    return x <= px < x + w and y <= py < y + h


def create_run(mode, rng):
    return GinRummyRun(mode, rng)
