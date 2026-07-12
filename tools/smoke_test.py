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
_tmp = tempfile.mkdtemp()
profile_mod.default_path = lambda: os.path.join(_tmp, "profile.json")

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
        app.draw_overlay_layer()
        app.renderer.finish(crt=True)
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

    # settings adjustments apply cleanly
    app.state = game_main.SETTINGS_SCREEN
    for idx in (0, 3, 4, 6, 8):
        app.settings_index = idx
        app.adjust_setting(idx, 1)
        render_frame()
    print("settings adjustments OK")

    # play every game/mode with its bot through the real app
    bots = {"voxelhell": dodge_bot_input, "breaker": breaker_bot,
            "serpent": serpent_bot}
    plans = [("voxelhell", "campaign"), ("voxelhell", "endless"),
             ("breaker", "arcade"), ("serpent", "arcade")]
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
            assert app.state == game_main.MENU

    app.game_id = "voxelhell"

    # force a loss -> run end screen renders, profile written
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
