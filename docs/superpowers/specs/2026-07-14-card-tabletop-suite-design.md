# Card / tabletop suite — design

Approved direction (2026-07-14; roadmap item after Battleship + Ambient). A **single-player /
non-multiplayer** suite of relaxing tabletop games in a new **TABLETOP** cabinet category, with
**heavy cosmetic customization** (deck skins + playmat/"felt" skins shared across the games).
Contrast with the shipped Battleship (the multiplayer capstone) — these are solo, cozy, and
achievement-rich.

Games (build order): **Solitaire (Klondike)** → **Rummy** → **Poker (video-poker / vs-AI)** →
**Backgammon** (board+dice, felt/board skins — not a deck). All Emberlight-themed.

## Why / feel
A rich solo tabletop corner of the cabinet: pick a deck and a felt, deal, and unwind. Cosmetics
are the point — *tons* of deck designs, many felts (plain, themed **galaxy**, and **dynamic /
animated** ones that reuse the ambient scenes), unlockables, and long-haul **grind achievements**
(e.g. Solitaire *1000 games played*).

## Rendering approach
Cards are flat, so the suite renders through the **overlay** (`OverlayRenderer`: `o.rect / o.text
/ o.image`, logical `UI_H=860`), like the board games' HUDs, over a backdrop. The backdrop IS the
**felt**: a solid/gradient wash for plain felts, or — for dynamic felts — an **ambient scene**
(`ambient.scenes`) drawn in the 3D pass, then cards on top. No new asset pipeline; a card is drawn
procedurally (rounded rect + rank/suit glyphs + pip layout), themed by the active **deck skin**.

## Shared kit: `games/cards/`
- `deck.py` (pure logic) — `Card(rank 1-13, suit in SHDC)`, color, label; `make_deck()`,
  `shuffle(deck, rng)`, deal helpers. JSON-serialisable (future replays).
- `skins.py` (pure data + registry) — **DeckSkin** (id, name, back style, pip/face palette,
  premium) and **FeltSkin** (id, name, kind = `solid|gradient|scene:<ambient_scene>`, colors,
  premium). Big DEFAULT lists (tons of decks, many felts incl. galaxy + dynamic), unlock-gating
  (`available_decks(unlocked)`, `available_felts(unlocked)`), reusing the achievement→unlock
  mechanism. Premium cosmetics tie to flagship / grind achievements (non-multiplayer).
- `render.py` (GL/overlay) — `draw_card(o, x, y, card, skin, face_up)`, `draw_pile`, `draw_back`,
  `draw_felt(renderer, felt, ambient_cache)` (solid/gradient wash or an ambient scene backdrop).
  A `CardTable` mixin/base gives shared felt draw + a pointer/keyboard **cursor** for pile/card
  selection.
- Selection input: pointer pick (mouse over card rects) with a keyboard/gamepad cursor fallback,
  themed hover highlight — mirrors the board kit's approach.

## Skin persistence & selection
Cosmetics are **global** across the tabletop games, stored in a new `profile["tabletop"]`:
`{deck, felt, unlocked_decks:[], unlocked_felts:[]}` (accessor backfills, like `ambient_section`).
A lightweight in-game **TABLE** customization screen (or an in-run panel, TAB) cycles deck + felt
among unlocked options and previews live. Unlocks are granted by achievements (per-game and grind).

## Solitaire (first slice)
Klondike: 7 tableau piles (i+1 cards, top face-up), stock+waste (draw 1; draw-3 as a setting),
4 suit foundations A→K. Moves: stock→waste (+ recycle), waste/tableau→tableau (descending,
alternating colour; empty pile takes a King), waste/tableau→foundation (up by suit), foundation→
tableau; auto-flip exposed face-down tops; **auto-to-foundation** convenience. Win = all 52 up.
Deterministic from a seed. Solo — no AI. Tracks grind counters in its profile section:
`games_played, games_won, best_time, current_streak, best_streak` (persisted on deal/complete).

### Solitaire achievements (incl. long grind)
`first_win`, `no_undo` (win without undo), `speed_run` (win under N min), `streak_3`, and grind:
`century` (100 games played), `millennium` (**1000 games played**), `founder` (250 wins). Grind
ones show progress bars. A couple of premium deck/felt skins unlock from these.

## Per-game notes (later increments)
- **Rummy** — draw/discard, meld sets/runs, vs a simple AI; hand + melds via the card kit.
- **Poker** — 5-card **video poker** (hold/draw, payout table) first — cleanest solo; optional
  heads-up vs-AI later. Hand evaluator in `games/cards/`.
- **Backgammon** — 24 points + bar/off, tumbling dice, pip-count greedy AI; uses **felt/board**
  skins (checkers + board), not deck skins. Rich animation.

## Modes & solo fallback
Every game is solo/offline. Difficulty/variant as a mode where useful (Solitaire draw-1/draw-3).
No networking, no online — deliberately (the multiplayer capstone is Battleship).

## Testing (headless, TDD)
- `deck`: 52 unique cards, deterministic shuffle, colors.
- `skins`: registry round-trip + unlock gating (premium hidden until its achievement).
- `solitaire/model`: deal shape (28 tableau, 24 stock), legal/illegal tableau + foundation moves,
  stock draw + recycle, auto-flip, win detection on a contrived near-win, deterministic replay of
  a scripted move list; grind counters increment on deal/complete.
- Scenes/render/wiring are GL — verified live (hidden-GL capture + `python main.py`).

## Non-goals
- Multiplayer / online (Battleship owns that). Real-money/gambling framing for Poker.
- A full Klondike solver (rules-correct, not auto-winnable). Custom user-drawn card art.

## Sequencing (increments)
1. **Card core + skins + Solitaire rules** — `games/cards/deck.py`, `games/cards/skins.py`,
   `games/solitaire/model.py`; `tools/test_cards.py` (all headless, TDD). No GL.
2. **Card render kit + Solitaire view/input** — `games/cards/render.py`, `games/solitaire/game.py`
   (INFO, GameRun, cursor, deal/win flow), register TABLETOP category. Verified live.
3. **Skin system UI + persistence** — `profile["tabletop"]`, deck/felt selection (TABLE screen /
   in-run panel), dynamic felts via ambient scenes, unlock gating.
4. **Solitaire achievements + grind counters** — per-game + grind, progress bars, cosmetic unlocks.
5. **Rummy.** 6. **Poker (video poker).** 7. **Backgammon** (+ board/checker skins).
