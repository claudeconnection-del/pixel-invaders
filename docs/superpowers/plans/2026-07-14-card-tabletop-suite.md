# Card / tabletop suite — implementation plan

Spec: `docs/superpowers/specs/2026-07-14-card-tabletop-suite-design.md`. TDD; commit per
increment; message trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
Branch: `secret-local-multiplayer` (do not merge to main without asking).

**Goal:** a solo TABLETOP category with heavy cosmetic customization (deck + felt skins), proven
first by Solitaire, then Rummy / Poker / Backgammon.

## Global constraints
- Headless-testable core (deck, skins, rules) with no GL. Rendering/wiring is GL, verified live.
- Cosmetics are global (`profile["tabletop"]`); skins gate on achievements (reuse the mechanism).
- Follow existing patterns (arcade.game_api GameRun; overlay drawing; theme palette). No new deps.

## Increment 1 — card core + skins + Solitaire rules (headless, TDD)
- `games/cards/__init__.py`, `games/cards/deck.py` (Card, make_deck, shuffle, deal).
- `games/cards/skins.py` (DeckSkin, FeltSkin dataclasses; big DEFAULTS; `available_decks/felts`
  unlock gating; round-trip).
- `games/solitaire/__init__.py`, `games/solitaire/model.py` (Klondike: deal, legal moves, apply,
  stock draw/recycle, auto-flip, auto-to-foundation, win; grind-counter helpers pure of profile).
- `tools/test_cards.py`: deck, skins gating, solitaire deal/moves/recycle/win/determinism.
- Commit `feat(cards): deck + skins + Solitaire rules (headless core)`.

## Increment 2 — card render kit + Solitaire view/input (GL, live)
- `games/cards/render.py`: draw_card / draw_back / draw_pile / draw_felt (solid|gradient|scene).
- `games/solitaire/game.py`: INFO (TABLETOP), SolitaireRun (GameRun) — deal, cursor (mouse + keys),
  move/auto flows, win screen, new-deal (N). Register category in `games/__init__.py`.
- Verify via hidden-GL capture + smoke; commit `feat(solitaire): table render + play`.

## Increment 3 — skin system UI + persistence
- `meta/profile.py` `profile["tabletop"]` (deck/felt/unlocked) + accessor; deck/felt selection
  (in-run TAB panel and/or a TABLE menu entry), live preview; dynamic felts via `ambient.scenes`;
  unlock gating in the UI. Commit `feat(cards): deck/felt skin system + selection`.

## Increment 4 — Solitaire achievements + grind
- `games/solitaire/achievements.py` (first_win, speed_run, streak_3, no_undo, century, millennium,
  founder) with progress; grind counters persisted; cosmetic unlocks wired. Commit
  `feat(solitaire): achievements + grind counters`.

## Increment 5–7 — Rummy, Poker (video poker), Backgammon
- Each: rules (headless, TDD) → view/input → achievements; reuse the card/skin kit; Backgammon adds
  board/checker skins. Commit per game.

## Self-review
Spec coverage: TABLETOP category + solo suite (I2/I5-7), deck+felt skins incl. galaxy/dynamic
(I1 data, I3 UI + ambient-backed felts), Solitaire first (I1-I4), grind achievements (I4),
overlay card rendering (I2). Headless core fully testable before any GL (I1).
