"""App-level smoke test: boots the real cabinet against a hidden GL window,
drives every screen for every registered game, plays a stretch of each
game/mode with a bot where available, and checks persistence.

Run with: python tools/smoke_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# isolate the profile so smoke tests never touch the real save
import meta.profile as profile_mod  # noqa: E402
import meta.ghost as ghost_mod  # noqa: E402
import meta.replay as replay_mod  # noqa: E402
_tmp = tempfile.mkdtemp()
profile_mod.default_path = lambda: os.path.join(_tmp, "profile.json")
ghost_mod.default_path = lambda: os.path.join(_tmp, "ghosts.json")
replay_mod.REPLAY_DIR = os.path.join(_tmp, "replays")

import pygame  # noqa: E402


def main():
    import main as game_main
    from game.entities import InputState
    from games import GAME_IDS
    from tools.test_world import dodge_bot_input
    from tools.test_games import breaker_bot, serpent_bot

    # patch: hidden window instead of visible one (App sets GL attributes)
    real_set_mode = pygame.display.set_mode
    pygame.display.set_mode = lambda size, flags=0, **kw: real_set_mode(
        size, flags | pygame.HIDDEN)

    app = game_main.App()
    dt = 1 / 60

    def render_frame():
        app.update_timers(dt)
        app.renderer.begin(dt)
        app.draw_3d_layer(dt, 0.0)
        app.renderer.finish(crt=True)  # scene composites first...
        app.draw_overlay_layer()       # ...then crisp post-CRT overlay
        pygame.display.flip()

    # every cabinet screen for every game
    for gid in GAME_IDS:
        app.game_id = gid
        for state in (game_main.MENU, game_main.ACHIEVEMENTS_SCREEN,
                      game_main.STATS_SCREEN, game_main.SETTINGS_SCREEN):
            app.state = state
            for _ in range(2):
                render_frame()
        if app.game.INFO.has_skins:
            app.state = game_main.HANGAR
            for _ in range(len(app.game.SKIN_ORDER)):
                app.handle_keydown(pygame.K_RIGHT)
                render_frame()
        if len(app.game.INFO.modes) > 1:
            app.state = game_main.MODE_SELECT
            render_frame()
    print(f"cabinet screens OK for {GAME_IDS}")

    # menu nav regression: Down from PLAY must move even when HANGAR/SCORES
    # are hidden (studio), and category carousel must switch game groups
    from games import category_of
    app.game_id = "studio"
    app.state = game_main.MENU
    rows = app.menu_rows()
    assert "HANGAR" not in rows and "SCORES" not in rows
    app.menu_index = rows.index("PLAY")
    app.handle_keydown(pygame.K_DOWN)
    assert app.menu_rows()[app.menu_index] != "PLAY", \
        "Down from PLAY did not move selection"
    for _ in range(len(app.menu_rows()) + 2):  # full wrap both directions
        app.handle_keydown(pygame.K_DOWN)
    for _ in range(len(app.menu_rows()) + 2):
        app.handle_keydown(pygame.K_UP)
    app.menu_index = 0  # CATEGORY row
    before = category_of(app.game_id)
    app.handle_keydown(pygame.K_RIGHT)
    assert category_of(app.game_id) != before, "category did not switch"
    app.handle_keydown(pygame.K_LEFT)
    assert category_of(app.game_id) == before
    render_frame()
    print("menu navigation OK (hidden rows + categories)")

    # settings adjustments apply cleanly
    app.state = game_main.SETTINGS_SCREEN
    for idx in (0, 3, 4, 6, 8):
        app.settings_index = idx
        app.adjust_setting(idx, 1)
        render_frame()

    # profile export / import action rows (CAB-27): export writes a file, then
    # import confirms on the second press and swaps the profile back in.
    import meta.profile as _pm
    export_idx = next(i for i, r in enumerate(game_main.SETTINGS_ROWS)
                      if r[1] == "export_profile")
    import_idx = export_idx + 1
    app.profile["settings"]["player_name"] = "SMK"
    app.settings_index = export_idx
    app.adjust_setting(export_idx, 1)                # export
    render_frame()
    assert os.path.exists(_pm.export_path()), "export did not write a file"
    app.profile["settings"]["player_name"] = "AAA"   # change since export
    app.settings_index = import_idx
    app.adjust_setting(import_idx, 1)                # arm (first press)
    assert app._import_armed
    app.adjust_setting(import_idx, 1)                # confirm (second press)
    assert not app._import_armed
    assert app.profile["settings"]["player_name"] == "SMK"   # imported value
    render_frame()
    os.remove(_pm.export_path())                      # clean up the fixture
    print("settings adjustments OK (incl. profile export/import)")

    # music sequencer: pools discovered, sections shuffle without repeats
    for pool, minimum in (("menu", 3), ("game", 6), ("boss", 2)):
        assert len(app.audio.pools.get(pool, [])) >= minimum, \
            f"pool {pool} too small: {app.audio.pools.get(pool)}"
    app.audio.music("game")
    picks = [app.audio.recent[-1]]
    for _ in range(12):
        app.audio.on_music_end()  # simulate sections finishing
        picks.append(app.audio.recent[-1])
    assert all(a != b for a, b in zip(picks, picks[1:])), \
        "sequencer repeated a section back-to-back"
    assert len(set(picks)) >= 5, f"not enough variety: {sorted(set(picks))}"
    app.audio.music("boss")
    app.audio.on_music_end()
    assert "boss_" in os.path.basename(app.audio.recent[-1])
    app.audio.music(None)
    print(f"music sequencer OK ({len(set(picks))} distinct sections over "
          f"{len(picks)} plays)")

    # play every game/mode with its bot through the real app
    from games.aimtrainer.bot import demo_bot as aim_bot
    from games.crisis.bot import demo_bot as crisis_bot
    from games.voxeldoom.bot import demo_bot as doom_bot
    bots = {"voxelhell": dodge_bot_input, "breaker": breaker_bot,
            "serpent": serpent_bot, "aimtrainer": aim_bot,
            "voxeldoom": doom_bot, "crisis": crisis_bot}
    plans = [("voxelhell", "campaign"), ("voxelhell", "endless"),
             ("breaker", "arcade"), ("serpent", "arcade"),
             ("aimtrainer", "gridshot"), ("voxeldoom", "campaign"),
             ("crisis", "arcade")]
    for gid, mode in plans:
        app.game_id = gid
        app.state = game_main.MENU
        app.start_run(mode)
        assert app.state == game_main.PLAYING
        bot_fn = bots[gid]
        for frame in range(60 * 15):
            bot = bot_fn(app.run.world)
            app.gameplay_input = lambda b=bot: b
            app.update_playing(dt)
            render_frame()
            if app.state == game_main.RUN_END:
                break
        print(f"{gid} {mode} OK (state={app.state}, score={app.run.score})")
        # pause/resume then abandon cleanly
        if app.state == game_main.PLAYING:
            app.handle_keydown(pygame.K_ESCAPE)
            assert app.state == game_main.PAUSED
            render_frame()
            app.handle_keydown(pygame.K_ESCAPE)
            assert app.state == game_main.PLAYING
            app.handle_keydown(pygame.K_ESCAPE)
            app.handle_keydown(pygame.K_q)
            assert app.state == game_main.MENU
        elif app.state == game_main.RUN_END:
            app.handle_keydown(pygame.K_RETURN)
            if app.state == game_main.INITIALS:  # qualifying score: skip entry
                app.handle_keydown(pygame.K_ESCAPE)
            assert app.state == game_main.MENU, app.state

    app.game_id = "voxelhell"

    # Voxel Studio: params, preview, sequence slots, export -> custom pool
    import games.studio.game as studio_game
    studio_game.USERMUSIC_DIR = os.path.join(_tmp, "usermusic")
    import game.assets as assets_mod
    assets_mod.USERMUSIC_DIR = studio_game.USERMUSIC_DIR

    app.game_id = "studio"
    app.state = game_main.MENU
    app.start_run("studio")
    assert app.state == game_main.PLAYING
    run = app.run
    assert run.section is not None, "attach_profile hook not called"
    # walk every parameter row and adjust it
    for i in range(len(studio_game.PARAM_ROWS)):
        run.row = i
        run.handle_key(pygame.K_RIGHT)
        app.update_playing(dt)
        render_frame()
    run.handle_key(pygame.K_SPACE)   # bake + preview
    for _ in range(10):
        app.update_playing(dt)
        render_frame()
    for _ in range(4):               # build a 4-slot sequence
        run.handle_key(pygame.K_RETURN)
        app.update_playing(dt)
    run.handle_key(pygame.K_e)       # export as custom soundtrack
    app.update_playing(dt)
    render_frame()

    exported = sorted(os.listdir(studio_game.USERMUSIC_DIR))
    assert len(exported) == 4, f"expected 4 exported sections: {exported}"
    assert app.audio.prefer_custom and app.audio.pools.get("custom"), \
        "custom pool not active after export"
    assert app.audio._resolve("game") == "custom"
    saved = profile_mod.game_section(app.profile, "studio")["sequence"]
    assert len(saved) == 4, "sequence not persisted"
    unlocked = set(profile_mod.game_section(app.profile, "studio")["achievements"])
    assert {"first_bake", "arranger", "resident_composer"} <= unlocked, unlocked
    app.handle_keydown(pygame.K_ESCAPE)
    app.handle_keydown(pygame.K_q)   # exit studio to menu
    print(f"voxel studio OK (exported={len(exported)}, achievements={sorted(unlocked)})")

    # force a loss -> run end screen renders, profile written
    app.game_id = "voxelhell"
    app.start_run("campaign")
    app.run.world.player.lives = 1
    app.gameplay_input = lambda: InputState()
    for _ in range(60 * 60):
        app.update_playing(dt)
        render_frame()
        if app.state == game_main.RUN_END:
            break
    assert app.state == game_main.RUN_END, f"never reached RUN_END: {app.state}"
    for _ in range(3):
        render_frame()
    assert os.path.exists(profile_mod.default_path()), "profile not saved"
    loaded = profile_mod.load()
    section = profile_mod.game_section(loaded, "voxelhell")
    assert section["lifetime"]["runs"] >= 1
    print(f"run end + persistence OK (runs={section['lifetime']['runs']}, "
          f"achievements={sorted(section['achievements'])})")

    # the ended run was recorded as a replay and saved
    assert app.last_replay is not None and app.last_replay["dts"], \
        "run replay not recorded"
    rpath = replay_mod.last_path("voxelhell", app.run_mode)
    assert os.path.exists(rpath), "last-run replay not written"
    print(f"replay recorded OK ({len(app.last_replay['dts'])} frames, "
          f"seed={app.last_replay['seed']})")

    # initials entry -> leaderboard (score qualified since board is empty)
    assert app.pending_board is not None, "score should qualify for empty board"
    app.handle_keydown(pygame.K_RETURN)
    assert app.state == game_main.INITIALS
    render_frame()
    app.handle_keydown(pygame.K_DOWN)     # cycle a letter
    app.handle_keydown(pygame.K_RETURN)   # slot 2
    app.handle_keydown(pygame.K_RETURN)   # slot 3
    app.handle_keydown(pygame.K_RETURN)   # submit
    assert app.state == game_main.LEADERBOARD
    assert app.last_rank == 1
    render_frame()
    from meta.leaderboard import entries
    board = entries(app.profile, "voxelhell", "campaign")
    assert len(board) == 1 and board[0]["score"] > 0

    # outbox visibility (CAB-28): with the server unreachable (no base_url in
    # smoke), queued scores stay pending; the leaderboard surfaces the count +
    # R retries them.
    import meta.outbox as _ob
    assert not app.net.available            # smoke runs offline (empty server_url)
    app.profile["outbox"] = []              # start from a clean queue
    app.outbox.inflight.clear()
    app.state = game_main.LEADERBOARD
    app.outbox.queue_score("voxelhell", "campaign", "AAA", 123)
    app.outbox.queue_score("voxelhell", "campaign", "BBB", 456)
    pend = _ob.pending_count(app.profile)
    assert pend == 2, f"expected 2 pending, got {pend}"
    assert _ob.status_line(pend, False)     # non-empty status line
    render_frame()                          # draws the pending status line
    app.handle_keydown(pygame.K_r)          # retry now (offline -> stays queued)
    render_frame()
    assert app.wave_banner is not None      # retry feedback banner
    assert _ob.pending_count(app.profile) == 2   # still queued while offline
    app.handle_keydown(pygame.K_ESCAPE)
    assert app.state == game_main.MENU
    print(f"initials + leaderboard OK (entry={board[0]['name']} "
          f"{board[0]['score']}, {pend} pending surfaced)")

    # replay theater: browse the saved replay and watch it back in-engine.
    # Re-sim playback must advance the run and stay a read-only spectator view
    # (starts and ends at the menu, so it never disturbs the run-end flow).
    app.game_id = "voxelhell"
    app.open_replays()
    assert app.state == game_main.REPLAYS
    assert app.replays_list, "replay browser found no replays"
    render_frame()                          # exercise the browser draw path
    app.handle_keydown(pygame.K_RETURN)     # watch the newest replay
    assert app.state == game_main.REPLAYING
    for _ in range(60 * 6):                 # up to 6s of playback
        app.update_replay(dt)
        render_frame()
        if app.replay_view["done"]:
            break
    played = app.replay_view["accum"]
    assert played > 0, "replay did not advance"
    app.handle_keydown(pygame.K_SPACE)      # pause toggles cleanly
    assert app.replay_view["paused"]
    app.handle_keydown(pygame.K_ESCAPE)     # back to the browser
    assert app.state == game_main.REPLAYS
    app.handle_keydown(pygame.K_ESCAPE)     # back to the menu
    assert app.state == game_main.MENU
    assert app.replay_view is None, "replay view not released on exit"
    print(f"replay theater OK (watched {played:.1f}s of a saved run)")

    # attract mode: idle in, keypress out, cycles between games on demo death
    app.idle_timer = 999
    for _ in range(3):
        app.update_timers(dt)
        app.idle_timer += dt
        if app.state == game_main.MENU and app.idle_timer >= 15:
            app.start_attract()
        if app.state == game_main.ATTRACT:
            app.update_attract(dt)
        render_frame()
    assert app.state == game_main.ATTRACT
    for _ in range(120):
        app.update_attract(dt)
        render_frame()
    app.handle_keydown(pygame.K_SPACE)
    assert app.state == game_main.MENU
    print("attract mode OK")

    # Cabinet Man attract star: forcing the setting makes a live pilot star the
    # idle cycle (persona caption on), and it stays a throwaway — no profile
    # writes while a pilot demo plays (E1 integrity in attract).
    import copy as _copy
    app.profile["settings"]["attract_star"] = "cabinet_man"
    app.profile["settings"]["cabinet_man"] = True
    starred_pilot = False
    for _ in range(8):                       # cycle until a pilot-eligible game stars
        app.start_attract()
        if app.attract_is_pilot:
            starred_pilot = True
            break
    assert starred_pilot, "cabinet_man attract star never fielded a live pilot"
    assert app.attract_pilot is not None
    profile_before = _copy.deepcopy(app.profile)
    for _ in range(180):                     # ~3s of live pilot attract play
        app.update_attract(dt)
        render_frame()
        if app.state != game_main.ATTRACT:
            break
    assert app.profile == profile_before, "attract pilot wrote to the profile"
    app.handle_keydown(pygame.K_SPACE)
    assert app.state == game_main.MENU
    print(f"cabinet man attract star OK (pilot starred {app.attract_gid}, "
          f"no profile writes)")

    # ambient mode: manual entry (F2), draw the scene + overlay, any-key exit;
    # then the idle-screen routing that fades a quiet menu into ambient
    app.game_id = "voxelhell"
    app.state = game_main.MENU
    amb = profile_mod.ambient_section(app.profile)
    manual_before = amb["counters"]["manual_entries"]
    app.handle_keydown(pygame.K_F2)
    assert app.state == game_main.AMBIENT and not app.entered_auto
    for _ in range(30):
        app.update_ambient(dt)
        render_frame()               # exercises ambient 3D + overlay draw
    assert amb["counters"]["manual_entries"] == manual_before + 1
    assert app.ambient_session > 0 and amb["counters"]["total_seconds"] > 0

    # customization panel (manual only): open, tweak, save a custom slot, close
    app.handle_keydown(pygame.K_TAB)
    assert app.ambient_edit
    app.handle_keydown(pygame.K_DOWN)     # select a field
    app.handle_keydown(pygame.K_RIGHT)    # change its value (applies live)
    render_frame()                        # draws the panel
    custom_before = len(amb["custom"])
    app.handle_keydown(pygame.K_RETURN)   # save as custom slot
    assert len(amb["custom"]) == custom_before + 1
    assert amb["current"] == amb["custom"][-1]["id"]
    app.handle_keydown(pygame.K_TAB)      # close panel, stay in ambient
    assert not app.ambient_edit and app.state == game_main.AMBIENT

    app.handle_keydown(pygame.K_SPACE)   # any key returns to the menu
    assert app.state == game_main.MENU

    from ambient.preset import idle_target
    assert idle_target("attract") == "attract"
    assert idle_target("ambient") == "ambient"
    assert idle_target("off") is None
    app.profile["settings"]["idle_screen"] = "ambient"
    idle_before = amb["counters"]["idle_entries"]
    app.start_ambient(auto=True)          # what the MENU idle hook now does
    assert app.state == game_main.AMBIENT and app.entered_auto
    render_frame()                        # auto path draws the faint hint
    assert amb["counters"]["idle_entries"] == idle_before + 1
    app.handle_keydown(pygame.K_RETURN)
    assert app.state == game_main.MENU

    # sound: generated beds form a discoverable 'ambient' pool; a bed-backed
    # preset routes there (silence / music:<pool> handled the same way)
    assert len(app.audio.pools.get("ambient", [])) == 2, "ambient beds missing"
    amb["current"] = "fireplace"          # its default sound is bed:ambient
    app.start_ambient(auto=False)
    assert app.audio.current_pool == "ambient", "bed preset did not play the pool"
    app.handle_keydown(pygame.K_SPACE)
    assert app.state == game_main.MENU

    # premium unlock gating: Supernova is hidden until Voxel Hell's boss_slayer
    # achievement is earned, then it appears
    assert "supernova" not in {p.id for p in app._ambient_presets()}
    profile_mod.game_section(app.profile, "voxelhell")["achievements"][
        "boss_slayer"] = {"unlocked_at": "x"}
    assert "supernova" in {p.id for p in app._ambient_presets()}

    # mood achievement: ten unbroken minutes earns Deep Breath
    app.start_ambient(auto=False)
    app.ambient_session = 601
    app._check_ambient_achievements(amb)
    assert "deep_breath" in amb["achievements"]
    app.handle_keydown(pygame.K_SPACE)
    assert app.state == game_main.MENU
    print(f"ambient mode OK (manual + idle + bed + premium gate + mood, "
          f"{amb['counters']['total_seconds']:.1f}s)")

    # solitaire (TABLETOP): deal, draw the felt+cards, autoplay, new deal, and a
    # scripted win overlay; leaves cleanly via pause -> quit
    app.game_id = "solitaire"
    app.state = game_main.MENU
    app.start_run("draw1")
    assert app.state == game_main.PLAYING and len(app.run.model.stock) == 24
    sr = app.run
    for _ in range(4):
        app.gameplay_input = lambda: InputState()
        app.update_playing(dt)
        render_frame()                      # exercises felt + card draw
    sr.handle_key(pygame.K_SPACE)           # autoplay to foundations
    sr.handle_key(pygame.K_n)               # fresh deal
    assert sr.model.cards_home == 0 and len(sr.model.stock) == 24

    # skin picker (shared table.SkinPicker): TAB opens; cycle deck + felt
    sr.handle_key(pygame.K_TAB)
    assert sr.picker.open
    deck0 = sr.deck.id
    sr.handle_key(pygame.K_RIGHT)           # next deck
    sr.handle_key(pygame.K_DOWN)            # to the felt row
    felt0 = sr.felt.id
    sr.handle_key(pygame.K_RIGHT)           # next felt
    render_frame()                          # draws the panel + live preview
    assert sr.deck.id != deck0 and sr.felt.id != felt0
    tt = app.profile["settings"]["tabletop"]
    assert tt["deck"] == sr.deck.id and tt["felt"] == sr.felt.id
    # four-color accessibility toggle (third picker row)
    sr.handle_key(pygame.K_DOWN)            # to the Four-color row
    assert not sr.four_color
    sr.handle_key(pygame.K_RIGHT)           # toggle on
    render_frame()                          # preview redraws with 4-color ink
    assert sr.four_color and tt["four_color"] is True
    sr.handle_key(pygame.K_TAB)
    assert not sr.picker.open

    # rules overlay (H): opens, renders, closes; mutually exclusive with picker
    sr.handle_key(pygame.K_TAB)             # open the picker first
    assert sr.picker.open
    sr.handle_key(pygame.K_h)               # H closes the picker + opens rules
    assert sr.rules.open and not sr.picker.open
    render_frame()                          # draws the rules panel
    sr.handle_key(pygame.K_h)               # H closes it
    assert not sr.rules.open

    from games.cards.deck import Card
    full = lambda s: [Card(r, s) for r in range(1, 14)]
    sr.model.foundations = {"S": full("S"), "H": full("H"), "D": full("D"),
                            "C": [Card(r, "C") for r in range(1, 13)]}
    sr.model.tableau = [{"down": [], "up": [Card(13, "C")]}] + \
                       [{"down": [], "up": []} for _ in range(6)]
    sr.model.stock, sr.model.waste = [], []
    assert sr._solvable()                   # no face-down cards -> auto-complete
    app.handle_keydown(pygame.K_SPACE)      # solved board -> starts auto-complete
    assert sr.autocompleting
    app.gameplay_input = lambda: InputState()
    for _ in range(6):                      # auto-complete plays out to a win
        app.update_playing(dt)
        if sr.model.won:
            break
    assert sr.model.won and sr.won_flag and not sr.autocompleting
    render_frame()                          # draws the win overlay
    sol_sec = profile_mod.game_section(app.profile, "solitaire")
    assert "first_win" in sol_sec["achievements"] and sol_sec["lifetime"]["sol_wins"] >= 1
    app.update_playing(dt)                  # per-frame sync grants the cosmetic
    assert "ember_royale" in app.profile["settings"]["tabletop"]["unlocked_decks"]
    app.handle_keydown(pygame.K_ESCAPE)     # pause
    app.handle_keydown(pygame.K_q)          # quit to menu
    assert app.state == game_main.MENU
    print(f"solitaire OK (play / skins / auto-complete win + unlock, "
          f"{sol_sec['lifetime']['sol_games']} games)")

    # solitaire VEGAS mode (CAB-22): buy-in on deal, bank tracks foundation
    # gains, pass limit enforced, bankroll cumulative across deals.
    app.game_id = "solitaire"
    app.state = game_main.MENU
    app.start_run("vegas")
    vr = app.run
    assert vr.vegas and vr.model.pass_limit == 3 and vr.draw_count == 3
    vlife = profile_mod.game_section(app.profile, "solitaire")["lifetime"]
    assert vlife["sol_vegas_bank"] == -52          # opening buy-in
    vr.model.foundations["S"] = [Card(1, "S"), Card(2, "S"), Card(3, "S")]
    app.gameplay_input = lambda: InputState()
    app.update_playing(dt)                          # accrues +$15
    render_frame()                                  # draws the BANK readout
    assert vlife["sol_vegas_bank"] == -52 + 15
    vr.handle_key(pygame.K_n)                        # new deal: another -52
    assert vlife["sol_vegas_deals"] == 2 and vlife["sol_vegas_bank"] == -52 + 15 - 52
    app.handle_keydown(pygame.K_ESCAPE)
    app.handle_keydown(pygame.K_q)
    assert app.state == game_main.MENU
    print(f"solitaire vegas OK (bank ${vlife['sol_vegas_bank']}, "
          f"{vlife['sol_vegas_deals']} deals)")

    # gin rummy (TABLETOP): deal, draw the table, drive human + house AI turns
    # until a hand resolves; exercises the meld engine, render, and result screen
    from games.rummy.model import deadwood as rm_dead
    app.game_id = "rummy"
    app.state = game_main.MENU
    app.start_run("gin")
    assert app.state == game_main.PLAYING
    rr = app.run
    app.gameplay_input = lambda: InputState()
    rr.handle_key(pygame.K_h)               # rules overlay opens + renders
    assert rr.rules.open
    render_frame()
    rr.handle_key(pygame.K_h)               # and closes
    assert not rr.rules.open
    app.update_playing(dt)                  # one real update tick (P1's turn)
    for _ in range(80):
        m = rr.model
        if m.hand_over:
            break
        if m.turn == "P1":
            if m.phase == "draw":
                m.draw("stock")
            else:
                worst = min(m.hands["P1"],
                            key=lambda c: rm_dead([x for x in m.hands["P1"] if x is not c]))
                knock = rm_dead([x for x in m.hands["P1"] if x is not worst]) <= 10
                m.discard_card(worst, knock=knock)
                if m.hand_over:
                    rr._announce()
        else:
            rr._house_turn()
        render_frame()                      # exercises felt + hands + piles draw
    assert all(len(rr.model.hands[p]) == 10 for p in ("P1", "P2"))
    if rr.model.hand_over:
        assert rr.model.result is not None
        render_frame()                      # draws the hand-result overlay
    app.handle_keydown(pygame.K_ESCAPE)
    app.handle_keydown(pygame.K_q)
    assert app.state == game_main.MENU
    print(f"gin rummy OK (hand_over={rr.model.hand_over}, "
          f"scores={rr.model.scores})")

    # video poker (TABLETOP): deal, toggle a hold, draw, exercise the bet
    # controls + rebuy path, and the table/paytable render.
    import games.poker.game as poker_game
    app.game_id = "poker"
    app.state = game_main.MENU
    app.start_run("jacks")
    assert app.state == game_main.PLAYING
    pr = app.run
    app.gameplay_input = lambda: InputState()
    credits0 = pr.model.credits
    app.handle_keydown(pygame.K_RIGHT)          # bet 1 -> 2
    assert pr.model.bet == 2
    app.handle_keydown(pygame.K_d)               # deal
    assert pr.model.phase == "hold" and pr.model.credits == credits0 - 2
    render_frame()                               # exercises hand + paytable draw
    app.handle_keydown(pygame.K_1)                # hold card 0
    assert pr.model.held[0]
    app.handle_keydown(pygame.K_d)                # draw
    assert pr.model.phase == "paid" and pr.model.last_result is not None
    render_frame()                                # winning-row highlight (if any)
    pr.model.credits = 0                          # force the rebuy path
    app.handle_keydown(pygame.K_r)
    assert pr.model.credits == poker_game.REBUY_AMOUNT
    poker_sec = profile_mod.game_section(app.profile, "poker")
    assert poker_sec["lifetime"]["vp_rebuys"] >= 1
    app.handle_keydown(pygame.K_ESCAPE)
    app.handle_keydown(pygame.K_q)
    assert app.state == game_main.MENU
    print(f"video poker OK (bet={pr.model.bet}, last={pr.model.last_result[0]}, "
          f"rebuys={poker_sec['lifetime']['vp_rebuys']})")

    # backgammon (TABLETOP): roll, click a source then a destination (driving
    # the real hit-test helpers, not the model directly) for several human
    # turns interleaved with house AI turns; assert checker conservation.
    app.game_id = "backgammon"
    app.state = game_main.MENU
    app.start_run("standard")
    assert app.state == game_main.PLAYING
    br = app.run
    br._W, br._H = 1280, 860
    app.gameplay_input = lambda: InputState()
    turns = 0
    guard = 0
    while turns < 6 and br.model.winner is None and guard < 500:
        guard += 1
        if br.model.turn == "A":
            if not br.model.dice:
                br._roll()
                render_frame()
                if not br.model.dice:      # no legal moves this roll: passed
                    turns += 1
                continue
            legal = br._legal_next_moves()
            if not legal:
                break
            mv = legal[0]
            src, dst = mv["from"], mv["to"]
            sx, sy, sw, sh = br._bar_rect() if src == "bar" else br._point_rect(src)
            br._click(sx + sw / 2, sy + sh / 2)
            dx, dy, dw, dh = (br._off_rect("A") if dst == "off"
                             else br._point_rect(dst))
            br._click(dx + dw / 2, dy + dh / 2)
            render_frame()               # exercises board/checker/dice draw
            if not br.model.dice:         # turn committed
                turns += 1
        else:
            app.update_playing(dt)        # drives the ~0.8s AI beat (roll, move)
            render_frame()
    assert br.model.checker_count("A") == 15 and br.model.checker_count("B") == 15
    app.handle_keydown(pygame.K_ESCAPE)
    app.handle_keydown(pygame.K_q)
    assert app.state == game_main.MENU
    print(f"backgammon OK ({turns} human turns driven, "
          f"pips A={br.model.pip_count('A')} B={br.model.pip_count('B')})")

    # Cabinet Man: F1 summons the house pilot on an opted-in game (Solitaire),
    # it plays a few moves on its own, then any real input instantly hands
    # back the seat — exercising summon -> pilot moves -> handback live.
    from games.cards.deck import Card as _Card
    app.game_id = "solitaire"
    app.state = game_main.MENU
    app.start_run("draw1")
    assert app.pilot is None and app.state == game_main.PLAYING
    cm = app.run
    full = lambda s: [_Card(r, s) for r in range(1, 14)]
    cm.model.foundations = {"S": full("S"), "H": full("H"), "D": full("D"),
                            "C": [_Card(r, "C") for r in range(1, 13)]}
    cm.model.tableau = [{"down": [], "up": [_Card(13, "C")]}] + \
                       [{"down": [], "up": []} for _ in range(6)]
    cm.model.stock, cm.model.waste = [], []
    cm.won_flag = False
    app.handle_keydown(pygame.K_F1)             # summon
    assert app.pilot is not None and app.wave_banner is not None
    app.gameplay_input = lambda: InputState()   # hands off the controls
    for _ in range(8):                          # the pilot plays on its own
        app.update_playing(dt)
        render_frame()                          # exercises the pulsing badge
        if cm.model.won:
            break
    assert cm.pilot_touched                      # the run is flagged
    pilot_won = cm.model.won
    app.handle_keydown(pygame.K_n)               # a real key: instant handback
    assert app.pilot is None
    print(f"cabinet man OK (pilot won={pilot_won}, pilot_touched={cm.pilot_touched})")

    # Cabinet Man on a SIM game (Voxel Hell): the pilot returns a synthesized
    # InputState that main.py feeds into the run instead of the human's — so
    # this exercises the other pilot path (fire/dodge bits, not direct model
    # actions). Summon, let it play + shoot, confirm the run is flagged and a
    # real key hands back.
    app.game_id = "voxelhell"
    app.state = game_main.MENU
    app.start_run("campaign")
    assert app.pilot is None and app.state == game_main.PLAYING
    vh = app.run
    app.gameplay_input = lambda: InputState()    # neutral human input
    app.handle_keydown(pygame.K_F1)              # summon Cabinet Man
    assert app.pilot is not None
    for _ in range(240):                         # ~4s: enough to line up + fire
        app.update_playing(dt)
        if app.run.world.stats["shots"] > 0:
            break
    render_frame()                               # exercises the HUD + badge
    assert vh.pilot_touched
    vh_shots = vh.world.stats["shots"]
    assert vh_shots > 0, "pilot never fired on voxelhell"
    # shot economy: any shots-hits gap is only bullets still in flight (the
    # just-fired one hasn't landed yet) — never a settled miss.
    settled = (vh.world.stats["shots"] - vh.world.stats["hits"]
               - len(vh.world.player_bullets))
    assert settled <= 0, f"voxelhell pilot settled a miss ({settled})"
    app.handle_keydown(pygame.K_LEFT)            # a real key: instant handback
    assert app.pilot is None
    print(f"cabinet man (voxel hell) OK (fired {vh_shots}, no settled miss, handback)")

    # Cabinet Man on Serpent: the safety-checked, glyph-tracing snake. Summon,
    # let it play a good while, confirm it grew, stayed alive, and traced glyphs.
    app.game_id = "serpent"
    app.state = game_main.MENU
    app.start_run("arcade")
    assert app.pilot is None and app.state == game_main.PLAYING
    sp = app.run
    app.gameplay_input = lambda: InputState()
    app.handle_keydown(pygame.K_F1)              # summon
    assert app.pilot is not None
    start_len = sp.world.length
    for _ in range(60 * 20):                     # ~20s of play
        app.update_playing(dt)
        if sp.world.run_over:
            break
    render_frame()                               # exercises the snake draw + badge
    assert sp.pilot_touched
    assert not sp.world.run_over, "serpent pilot died during the smoke window"
    assert sp.world.length > start_len, "serpent pilot never grew"
    glyphs = app.pilot.glyph_moves
    assert glyphs > 0, "serpent pilot never traced a glyph"
    app.handle_keydown(pygame.K_UP)              # a real key: instant handback
    assert app.pilot is None
    print(f"cabinet man (serpent) OK (grew {start_len}->{sp.world.length}, "
          f"{glyphs} glyph moves, alive, handback)")

    pygame.quit()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
