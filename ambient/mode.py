"""AmbientMode — the runtime engine for a calm ambient scene. Owns the active
preset + elapsed time; the cabinet dispatches it like ATTRACT (update + draw +
overlay). Pure of main.py state so it can be driven/tested in isolation.

Draw is a 3D scene (no arena walls); the overlay only draws a faint dismissible
hint when entered automatically (manual entry is chrome-free). Sound is resolved
from the preset: silence, an existing music pool, or (I5) a synthesized bed.
"""
from render.renderer import Batcher

from ambient.scenes import SCENES, SCENE_STARS


class AmbientMode:
    def __init__(self, preset):
        self.preset = preset
        self.t = 0.0

    def set_preset(self, preset):
        """Swap the live preset (customization / cycling) without resetting t."""
        self.preset = preset

    # ------------------------------------------------------------ frame
    def update(self, dt):
        self.t += dt

    def draw(self, renderer):
        b = Batcher()
        fn = SCENES.get(self.preset.scene, SCENES["starfield"])
        fn(self.preset, self.t, renderer, b)
        renderer.draw_scene(b, walls=False,
                            stars=SCENE_STARS.get(self.preset.scene, True))

    def draw_overlay(self, o, w, h, auto):
        from game import theme
        dim = max(0.0, min(0.85, self.preset.dim or 0.0))
        if dim > 0:
            o.rect(0, 0, w, h, (0, 0, 0, int(dim * 255)))
        if auto:  # manual entry stays completely chrome-free
            o.text("AMBIENT · press any key to return", w / 2, h - 40, size=15,
                   color=(theme.DIM[0], theme.DIM[1], theme.DIM[2], 150),
                   center=True)

    # ------------------------------------------------------------ sound
    def start_sound(self, audio):
        """Begin the preset's soundscape: silence, an existing music pool
        (`music:<pool>`), or a calm ambient bed (`bed:*` → the shuffling
        'ambient' pool of generated beds)."""
        snd = self.preset.sound or "silence"
        if snd.startswith("music:"):
            audio.music(snd.split(":", 1)[1])
        elif snd.startswith("bed:"):
            audio.music("ambient")
        else:
            audio.music(None)

    def stop_sound(self, audio):
        audio.music(None)
