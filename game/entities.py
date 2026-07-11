"""Entity classes for Pixel Invaders."""
import pygame

SCREEN_WIDTH = 640
SCREEN_HEIGHT = 720


class Bullet:
    def __init__(self, x, y, vy, image, from_player):
        self.rect = image.get_rect(center=(x, y))
        self.vy = vy
        self.image = image
        self.from_player = from_player
        self.alive = True

    def update(self, dt):
        self.rect.y += int(self.vy * dt)
        if self.rect.bottom < 0 or self.rect.top > SCREEN_HEIGHT:
            self.alive = False

    def draw(self, surface):
        surface.blit(self.image, self.rect)


class Player:
    def __init__(self, image, x, y):
        self.image = image
        self.rect = image.get_rect(midbottom=(x, y))
        self.speed = 260
        self.lives = 3
        self.cooldown = 0.0
        self.fire_delay = 0.45
        self.alive = True

    def update(self, dt, keys):
        dx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        self.rect.x += int(dx * self.speed * dt)
        self.rect.left = max(0, self.rect.left)
        self.rect.right = min(SCREEN_WIDTH, self.rect.right)
        if self.cooldown > 0:
            self.cooldown -= dt

    def can_shoot(self):
        return self.cooldown <= 0

    def shoot(self):
        self.cooldown = self.fire_delay

    def draw(self, surface):
        surface.blit(self.image, self.rect)


class Enemy:
    def __init__(self, kind, frames, x, y, points):
        self.kind = kind
        self.frames = frames  # (frame_a, frame_b)
        self.frame_index = 0
        self.rect = frames[0].get_rect(topleft=(x, y))
        self.points = points
        self.alive = True

    @property
    def image(self):
        return self.frames[self.frame_index]

    def toggle_frame(self):
        self.frame_index = 1 - self.frame_index

    def draw(self, surface):
        surface.blit(self.image, self.rect)


class Barrier:
    """A destructible barrier made of a small grid of blocks, each block is
    a chunk of the barrier sprite; blocks are removed as they take hits."""

    BLOCK_SIZE = 16
    COLS = 4
    ROWS = 4

    def __init__(self, block_image, x, y):
        self.block_image = block_image
        self.x = x
        self.y = y
        self.blocks = [
            [True for _ in range(self.COLS)] for _ in range(self.ROWS)
        ]

    def rects(self):
        for r in range(self.ROWS):
            for c in range(self.COLS):
                if self.blocks[r][c]:
                    yield (
                        r,
                        c,
                        pygame.Rect(
                            self.x + c * self.BLOCK_SIZE,
                            self.y + r * self.BLOCK_SIZE,
                            self.BLOCK_SIZE,
                            self.BLOCK_SIZE,
                        ),
                    )

    def hit(self, r, c):
        self.blocks[r][c] = False

    def is_empty(self):
        return not any(any(row) for row in self.blocks)

    def draw(self, surface):
        sub_w = self.block_image.get_width() // self.COLS
        sub_h = self.block_image.get_height() // self.ROWS
        for r, c, rect in self.rects():
            src = pygame.Rect(c * sub_w, r * sub_h, sub_w, sub_h)
            surface.blit(self.block_image, rect, src)


class Explosion:
    def __init__(self, image, center, duration=0.25):
        self.image = image
        self.rect = image.get_rect(center=center)
        self.timer = duration
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.alive = False

    def draw(self, surface):
        surface.blit(self.image, self.rect)
