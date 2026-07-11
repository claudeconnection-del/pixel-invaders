"""App-level smoke test: boots the real App against a hidden GL window,
drives every screen, plays a stretch of the campaign with the test bot,
and forces both run endings. Catches wiring errors before committing.

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
    from tools.test_world import dodge_bot_input

    # patch: hidden window instead of visible one (App sets GL attributes)
    real_set_mode = pygame.display.set_mode
    pygame.display.set_mode = lambda size, flags=0, **kw: real_set_mode(
        size, flags | pygame.HIDDEN)

    app = game_main.App()
    dt = 1 / 60

    def render_frame():
        app.update_timers(dt)
        app.renderer.begin(dt)
        if app.state in (game_main.PLAYING, game_main.PAUSED, game_main.RUN_END) \
                and app.world is not None:
            app.renderer.draw_world(app.world, app.profile["selected_skin"])
        else:
            app.renderer.draw_starfield_only()
        app.renderer.begin_overlay()
        if app.state == game_main.MENU:
            app.draw_menu()
        elif app.state == game_main.SKINS_SCREEN:
            app.draw_skins()
        elif app.state == game_main.ACHIEVEMENTS_SCREEN:
            app.draw_achievements()
        elif app.state == game_main.STATS_SCREEN:
            app.draw_stats()
        elif app.state in (game_main.PLAYING, game_main.PAUSED):
            app.draw_hud()
            if app.state == game_main.PAUSED:
                app.draw_paused()
        elif app.state == game_main.RUN_END:
            app.draw_run_end()
        app.renderer.finish(crt=True)
        pygame.display.flip()

    # menu screens render without crashing
    for state in (game_main.MENU, game_main.ACHIEVEMENTS_SCREEN,
                  game_main.STATS_SCREEN, game_main.SKINS_SCREEN):
        app.state = state
        for _ in range(3):
            render_frame()
    print("menu screens OK")

    # skin browsing
    app.state = game_main.SKINS_SCREEN
    for _ in range(len(game_main.SKIN_ORDER)):
        app.handle_keydown(pygame.K_RIGHT)
        render_frame()
    print("skin browsing OK")

    # play ~20 seconds of campaign with the bot
    app.state = game_main.MENU
    app.start_run()
    assert app.state == game_main.PLAYING
    for frame in range(60 * 20):
        bot = dodge_bot_input(app.world)
        app.gameplay_input = lambda b=bot: b
        app.update_playing(dt)
        render_frame()
        if app.state == game_main.RUN_END:
            break
    print(f"gameplay OK (state={app.state}, score={app.world.score}, "
          f"kills={app.world.stats['kills']})")

    # pause/resume
    if app.state == game_main.PLAYING:
        app.handle_keydown(pygame.K_ESCAPE)
        assert app.state == game_main.PAUSED
        render_frame()
        app.handle_keydown(pygame.K_ESCAPE)
        assert app.state == game_main.PLAYING
        print("pause/resume OK")

    # force a loss -> run end screen renders, profile written
    app.world.player.lives = 1
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
    assert loaded["lifetime"]["runs"] >= 1
    print(f"run end + profile persistence OK "
          f"(runs={loaded['lifetime']['runs']}, kills={loaded['lifetime']['kills']}, "
          f"achievements={sorted(loaded['achievements'])})")

    pygame.quit()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
