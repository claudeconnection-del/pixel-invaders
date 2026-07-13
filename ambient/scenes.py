"""Generative ambient scenes — calm, palette-driven cube fields built on the
existing voxel renderer (Batcher + starfield + bloom). Each scene is a pure
function `fn(preset, t, renderer, b)` that fills a Batcher `b` for frame time
`t`; motion is deterministic (per-element phase from a hash, so no per-frame
state) and honours `preset.speed`, `preset.density`, and `preset.palette`.

Field coords span ~[0,640]x[0,720] at the default camera; scenes overfill to
about [-200,840] so ultrawide edges stay covered. `SCENE_STARS` says whether the
drifting starfield backdrop shows behind a given scene.
"""
import math

from render.renderer import Batcher

_DENSITY = {"low": 0.5, "medium": 1.0, "high": 1.7}


def _h(i, s=0.0):
    """Stable pseudo-random 0..1 from an integer index + salt (no state)."""
    x = math.sin(i * 12.9898 + s * 78.233) * 43758.5453
    return x - math.floor(x)


def _count(preset, base):
    return max(6, int(base * _DENSITY.get(preset.density, 1.0)))


def _emit(rgb, k=1.4, a=1.0):
    """Palette [r,g,b] 0-255 -> emissive voxel tint (k>1 glows)."""
    return (rgb[0] / 255 * k, rgb[1] / 255 * k, rgb[2] / 255 * k, a)


def _pal(preset, i):
    p = preset.palette or [[238, 169, 76]]
    return p[i % len(p)]


def embers(preset, t, r, b):
    """Warm motes rising and drifting, brightest low, fading as they climb."""
    n = _count(preset, 120)
    sp = preset.speed
    span = 900.0
    for i in range(n):
        hx, hs, hz = _h(i, 1), _h(i, 3), _h(i, 5)
        yy = 720 - ((t * (30 + 60 * hs) * sp + hx * span) % span)  # rise + loop
        xx = -200 + hx * 1040 + math.sin(t * 0.6 * sp + hx * 6.283) * 30
        prog = (720 - yy) / span
        alpha = max(0.05, (1.0 - prog) * 0.95)
        b.add_cube_late(xx, yy, 0.16 + hs * 0.18, tint=_emit(_pal(preset, i), 1.7, alpha),
                        z=(hz - 0.5) * 4)


def starfield(preset, t, r, b):
    """Slow cool drift over the renderer's own starfield — bright motes that
    twinkle as they cross."""
    n = _count(preset, 90)
    sp = preset.speed
    for i in range(n):
        hx, hy, hp = _h(i, 1), _h(i, 2), _h(i, 7)
        xx = -200 + hx * 1040
        yy = ((hy * 900 + t * 8 * sp) % 900) - 90
        tw = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * (0.6 + hp) * sp + hp * 6.283))
        b.add_cube_late(xx, yy, 0.11 + hp * 0.16, tint=_emit(_pal(preset, i), 1.7, tw),
                        z=(hp - 0.5) * 7)


def aurora(preset, t, r, b):
    """Flowing horizontal bands that undulate — a slow curtain of light."""
    cols = _count(preset, 74)
    sp = preset.speed
    bands = 3
    for band in range(bands):
        col = _pal(preset, band)
        yb = 210 + band * 150
        for i in range(cols):
            fx = -200 + (i / cols) * 1040
            phase = fx * 0.012 + band * 1.7
            yy = yb + math.sin(t * 0.7 * sp + phase) * 66 + math.sin(t * 0.3 * sp + phase * 2) * 26
            alpha = 0.3 + 0.45 * (0.5 + 0.5 * math.sin(t * sp + phase))
            b.add_cube_late(fx, yy, 0.27, tint=_emit(col, 1.5, alpha), z=-band * 1.5)


def rain(preset, t, r, b):
    """Cool streaks falling with a slight slant."""
    n = _count(preset, 150)
    sp = preset.speed
    span = 940.0
    for i in range(n):
        hx, hspd = _h(i, 1), _h(i, 4)
        speed = (220 + 200 * hspd) * sp
        yy = ((hx * span + t * speed) % span) - 110
        xx = -200 + hx * 1040 + yy * 0.12  # slant with fall
        b.add("cube", xx, yy, 0.09 + 0.09 * hspd, tint=_emit(_pal(preset, i), 1.3, 0.7),
              z=(_h(i, 6) - 0.5) * 3)


def nebula(preset, t, r, b):
    """A slow luminous swirl around the centre — calm rotating spiral arms."""
    n = _count(preset, 210)
    sp = preset.speed
    for i in range(n):
        ha, hr, hz = _h(i, 1), _h(i, 2), _h(i, 8)
        arm = (i % 3) * (math.tau / 3)
        radius = 60 + hr * 470
        ang = arm + ha * 0.6 + t * (0.12 + 0.22 * (1 - hr)) * sp + radius * 0.004
        xx = 320 + math.cos(ang) * radius
        yy = 360 + math.sin(ang) * radius * 0.7
        alpha = 0.25 + 0.55 * (1 - hr)
        b.add_cube_late(xx, yy, 0.15 + (1 - hr) * 0.2,
                        tint=_emit(_pal(preset, i), 1.6, alpha), z=(hz - 0.5) * 5)


def fireplace(preset, t, r, b):
    """A concentrated bed of flame at the base — dense warm flicker with sparks
    lifting off."""
    n = _count(preset, 150)
    sp = preset.speed
    for i in range(n):
        hx, hs, hf = _h(i, 1), _h(i, 3), _h(i, 9)
        flick = 0.5 + 0.5 * math.sin(t * (5 + 4 * hf) * sp + hf * 6.283)
        base_x = 140 + hx * 360
        lift = ((t * (30 + 90 * hs) * sp + hx * 340) % 340)
        yy = 690 - lift
        xx = base_x + math.sin(t * 2 * sp + hx * 6.283) * (10 + lift * 0.07)
        alpha = max(0.06, (1.0 - lift / 340) * (0.5 + 0.5 * flick))
        b.add_cube_late(xx, yy, 0.14 + hs * 0.16 * flick,
                        tint=_emit(_pal(preset, i), 1.95, alpha), z=(_h(i, 6) - 0.5) * 3)


def equalizer(preset, t, r, b):
    """Premium: a row of gently pulsing voxel bars (a nod to Voxel Studio's
    equalizer). Non-reactive for now — driven by time, not audio."""
    bars = _count(preset, 22)
    sp = preset.speed
    base_y = 560
    for c in range(bars):
        fx = -160 + (c / max(1, bars - 1)) * 960
        h01 = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * (1.4 + 0.15 * c) * sp + c * 0.7))
        height = int(2 + h01 * 12)
        col = _pal(preset, c)
        for j in range(height):
            yy = base_y - j * 34
            alpha = 0.4 + 0.5 * (j / max(1, height))
            b.add_cube_late(fx, yy, 0.28, tint=_emit(col, 1.5, alpha))


SCENES = {
    "embers": embers,
    "starfield": starfield,
    "aurora": aurora,
    "rain": rain,
    "nebula": nebula,
    "fireplace": fireplace,
    "equalizer": equalizer,
}

# whether the renderer's drifting starfield shows behind the scene
SCENE_STARS = {
    "embers": False,
    "starfield": True,
    "aurora": True,
    "rain": False,
    "nebula": True,
    "fireplace": False,
    "equalizer": False,
}
