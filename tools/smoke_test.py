"""Headless smoke test: initializes the game and runs a few simulated frames
without opening a real window/audio device, to catch import/runtime errors
before committing. Not part of the shipped game.
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import Game, STATE_PLAYING  # noqa: E402


def run():
    game = Game()
    game.state = STATE_PLAYING
    for _ in range(180):  # simulate 3 seconds at 60fps
        game.update(1 / 60)
        game.draw()
        if game.state != STATE_PLAYING:
            print(f"game ended early with state={game.state}, score={game.score}")
            break
    print("smoke test completed OK; final state:", game.state, "score:", game.score)


if __name__ == "__main__":
    run()
