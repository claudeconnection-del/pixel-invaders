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
    print("settings adjustments OK")

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
    app.handle_keydown(pygame.K_ESCAPE)
    assert app.state == game_main.MENU
    print(f"initials + leaderboard OK (entry={board[0]['name']} "
          f"{board[0]['score']})")

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

    pygame.quit()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
