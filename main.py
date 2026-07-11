"""Pixel Invaders - a small 8-bit-style Space Invaders clone built with pygame.

Controls:
    Left/Right or A/D - move
    Space             - shoot
    Enter             - start / restart
    Esc               - quit
"""
import os
import random
import sys

import pygame

from game.assets import Assets
from game.entities import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    Player,
    Enemy,
    Bullet,
    Barrier,
    Explosion,
)

FPS = 60
HIGHSCORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscore.txt")

BG_COLOR = (10, 10, 18)
HUD_COLOR = (140, 255, 170)

ENEMY_ROWS = [
    ("octo", 30),
    ("crab", 20),
    ("crab", 20),
    ("squid", 10),
    ("squid", 10),
]
ENEMY_COLS = 8
ENEMY_H_SPACING = 72
ENEMY_V_SPACING = 80
ENEMY_START_X = 32
ENEMY_START_Y = 70

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAMEOVER = "gameover"
STATE_WIN = "win"


def load_highscore():
    try:
        with open(HIGHSCORE_PATH, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_highscore(value):
    try:
        with open(HIGHSCORE_PATH, "w") as f:
            f.write(str(value))
    except OSError:
        pass


class Game:
    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass  # no audio device available; game still runs silently

        pygame.display.set_caption("Pixel Invaders")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.SysFont("couriernew", 48, bold=True)
        self.font_med = pygame.font.SysFont("couriernew", 24, bold=True)
        self.font_small = pygame.font.SysFont("couriernew", 16, bold=True)

        self.assets = Assets()
        self.assets.load()

        self.highscore = load_highscore()
        self.state = STATE_MENU
        self.reset()

    def reset(self):
        img = self.assets.images
        self.player = Player(img["player"], SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)
        self.player_bullets = []
        self.enemy_bullets = []
        self.explosions = []
        self.score = 0
        self.enemy_direction = 1
        self.enemy_speed = 20.0
        self.enemy_step_timer = 0.0
        self.enemy_step_interval = 0.9
        self.step_sound_index = 0
        self.enemy_fire_timer = 1.0

        self.enemies = []
        frame_map = {
            "squid": (img["enemy_squid_a"], img["enemy_squid_b"]),
            "crab": (img["enemy_crab_a"], img["enemy_crab_b"]),
            "octo": (img["enemy_octo_a"], img["enemy_octo_b"]),
        }
        for row, (kind, points) in enumerate(ENEMY_ROWS):
            for col in range(ENEMY_COLS):
                x = ENEMY_START_X + col * ENEMY_H_SPACING
                y = ENEMY_START_Y + row * ENEMY_V_SPACING
                self.enemies.append(Enemy(kind, frame_map[kind], x, y, points))

        barrier_img = img["barrier"]
        gap = SCREEN_WIDTH // 4
        self.barriers = [
            Barrier(barrier_img, gap * i + gap // 2 - 32, SCREEN_HEIGHT - 160)
            for i in range(4)
        ]

    # ------------------------------------------------------------------
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)  # clamp to avoid huge steps if window stalls
            if not self.handle_events():
                break
            if self.state == STATE_PLAYING:
                self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit(0)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_RETURN:
                    if self.state in (STATE_MENU, STATE_GAMEOVER, STATE_WIN):
                        self.reset()
                        self.state = STATE_PLAYING
                if event.key == pygame.K_SPACE and self.state == STATE_PLAYING:
                    self.try_player_shoot()
        return True

    def try_player_shoot(self):
        if self.player.alive and self.player.can_shoot():
            self.player.shoot()
            bullet_img = self.assets.images["bullet_player"]
            b = Bullet(self.player.rect.centerx, self.player.rect.top, -520, bullet_img, True)
            self.player_bullets.append(b)
            self.assets.play("shoot")

    # ------------------------------------------------------------------
    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)

        for b in self.player_bullets:
            b.update(dt)
        for b in self.enemy_bullets:
            b.update(dt)
        self.player_bullets = [b for b in self.player_bullets if b.alive]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]

        for e in self.explosions:
            e.update(dt)
        self.explosions = [e for e in self.explosions if e.alive]

        self.update_enemies(dt)
        self.update_enemy_fire(dt)
        self.check_collisions()

        if not self.enemies:
            self.state = STATE_WIN
            self.assets.play("win")
            self._maybe_save_highscore()
        elif not self.player.alive:
            self.state = STATE_GAMEOVER
            self.assets.play("game_over")
            self._maybe_save_highscore()
        elif any(e.rect.bottom >= self.player.rect.top for e in self.enemies):
            self.player.alive = False
            self.state = STATE_GAMEOVER
            self.assets.play("game_over")
            self._maybe_save_highscore()

    def _maybe_save_highscore(self):
        if self.score > self.highscore:
            self.highscore = self.score
            save_highscore(self.highscore)

    def update_enemies(self, dt):
        if not self.enemies:
            return
        self.enemy_step_timer += dt
        # speed up as fewer enemies remain (classic invaders feel)
        alive_ratio = len(self.enemies) / (len(ENEMY_ROWS) * ENEMY_COLS)
        self.enemy_step_interval = 0.15 + 0.75 * alive_ratio

        if self.enemy_step_timer < self.enemy_step_interval:
            return
        self.enemy_step_timer = 0.0

        min_x = min(e.rect.left for e in self.enemies)
        max_x = max(e.rect.right for e in self.enemies)
        step = 14

        will_hit_edge = (
            max_x + step * self.enemy_direction > SCREEN_WIDTH
            or min_x + step * self.enemy_direction < 0
        )

        if will_hit_edge:
            for e in self.enemies:
                e.rect.y += 18
                e.toggle_frame()
            self.enemy_direction *= -1
        else:
            for e in self.enemies:
                e.rect.x += step * self.enemy_direction
                e.toggle_frame()

        self.assets.play(f"step_{self.step_sound_index}")
        self.step_sound_index = (self.step_sound_index + 1) % 4

    def update_enemy_fire(self, dt):
        if not self.enemies:
            return
        self.enemy_fire_timer -= dt
        if self.enemy_fire_timer <= 0:
            self.enemy_fire_timer = random.uniform(0.5, 1.3)
            shooter = random.choice(self.enemies)
            bullet_img = self.assets.images["bullet_enemy"]
            b = Bullet(shooter.rect.centerx, shooter.rect.bottom, 260, bullet_img, False)
            self.enemy_bullets.append(b)

    def check_collisions(self):
        img_explosion = self.assets.images["explosion"]

        # player bullets vs enemies
        for b in self.player_bullets:
            if not b.alive:
                continue
            for e in self.enemies:
                if e.alive and b.rect.colliderect(e.rect):
                    e.alive = False
                    b.alive = False
                    self.score += e.points
                    self.explosions.append(Explosion(img_explosion, e.rect.center))
                    self.assets.play("explosion_enemy")
                    break
        self.enemies = [e for e in self.enemies if e.alive]

        # player bullets vs barriers
        for b in self.player_bullets:
            if not b.alive:
                continue
            self._bullet_vs_barriers(b)

        # enemy bullets vs barriers
        for b in self.enemy_bullets:
            if not b.alive:
                continue
            self._bullet_vs_barriers(b)

        # enemy bullets vs player
        for b in self.enemy_bullets:
            if b.alive and self.player.alive and b.rect.colliderect(self.player.rect):
                b.alive = False
                self.player.lives -= 1
                self.explosions.append(Explosion(img_explosion, self.player.rect.center))
                self.assets.play("explosion_player")
                if self.player.lives <= 0:
                    self.player.alive = False

        self.player_bullets = [b for b in self.player_bullets if b.alive]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]

    def _bullet_vs_barriers(self, b):
        for barrier in self.barriers:
            if barrier.is_empty():
                continue
            for r, c, rect in barrier.rects():
                if b.rect.colliderect(rect):
                    barrier.hit(r, c)
                    b.alive = False
                    return

    # ------------------------------------------------------------------
    def draw(self):
        self.screen.fill(BG_COLOR)

        if self.state == STATE_MENU:
            self.draw_menu()
        else:
            self.draw_playfield()
            if self.state == STATE_GAMEOVER:
                self.draw_center_text("GAME OVER", "Press Enter to play again")
            elif self.state == STATE_WIN:
                self.draw_center_text("YOU WIN!", "Press Enter to play again")

        pygame.display.flip()

    def draw_playfield(self):
        for barrier in self.barriers:
            barrier.draw(self.screen)
        for e in self.enemies:
            e.draw(self.screen)
        for b in self.player_bullets:
            b.draw(self.screen)
        for b in self.enemy_bullets:
            b.draw(self.screen)
        if self.player.alive:
            self.player.draw(self.screen)
        for ex in self.explosions:
            ex.draw(self.screen)
        self.draw_hud()

    def draw_hud(self):
        score_surf = self.font_small.render(f"SCORE {self.score:04d}", True, HUD_COLOR)
        high_surf = self.font_small.render(f"HIGH {self.highscore:04d}", True, HUD_COLOR)
        lives_surf = self.font_small.render(f"LIVES {max(self.player.lives, 0)}", True, HUD_COLOR)
        self.screen.blit(score_surf, (12, 8))
        self.screen.blit(high_surf, (SCREEN_WIDTH // 2 - high_surf.get_width() // 2, 8))
        self.screen.blit(lives_surf, (SCREEN_WIDTH - lives_surf.get_width() - 12, 8))

    def draw_menu(self):
        title = self.font_big.render("PIXEL INVADERS", True, HUD_COLOR)
        prompt = self.font_med.render("Press Enter to start", True, (230, 230, 230))
        controls = self.font_small.render(
            "Move: Left/Right or A/D   Shoot: Space   Quit: Esc", True, (160, 160, 170)
        )
        high_surf = self.font_small.render(f"High score: {self.highscore:04d}", True, HUD_COLOR)

        self.screen.blit(
            title, (SCREEN_WIDTH // 2 - title.get_width() // 2, SCREEN_HEIGHT // 2 - 140)
        )
        self.screen.blit(
            prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, SCREEN_HEIGHT // 2 - 40)
        )
        self.screen.blit(
            controls, (SCREEN_WIDTH // 2 - controls.get_width() // 2, SCREEN_HEIGHT // 2 + 20)
        )
        self.screen.blit(
            high_surf, (SCREEN_WIDTH // 2 - high_surf.get_width() // 2, SCREEN_HEIGHT // 2 + 60)
        )

        preview = self.assets.images["enemy_octo_a"]
        self.screen.blit(preview, (SCREEN_WIDTH // 2 - preview.get_width() // 2, SCREEN_HEIGHT // 2 - 220))

    def draw_center_text(self, big, small):
        big_surf = self.font_big.render(big, True, HUD_COLOR)
        small_surf = self.font_med.render(small, True, (230, 230, 230))
        score_surf = self.font_med.render(f"Score: {self.score:04d}", True, (230, 230, 230))

        self.screen.blit(
            big_surf, (SCREEN_WIDTH // 2 - big_surf.get_width() // 2, SCREEN_HEIGHT // 2 - 80)
        )
        self.screen.blit(
            score_surf, (SCREEN_WIDTH // 2 - score_surf.get_width() // 2, SCREEN_HEIGHT // 2 - 10)
        )
        self.screen.blit(
            small_surf, (SCREEN_WIDTH // 2 - small_surf.get_width() // 2, SCREEN_HEIGHT // 2 + 30)
        )


def main():
    Game().run()


if __name__ == "__main__":
    main()
