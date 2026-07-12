"""Bakes all sound effects and the shipped music bank (assets/sfx,
assets/music) using the shared composition engine in game/composer.py.
Stdlib only. Run with: python tools/gen_sound.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.composer import (  # noqa: E402
    SectionSpec, build_section, chord_tones, concat, envelope, midi, mix,
    noise, note_track, square_wave, sweep, write_wav, PROGRESSIONS, REST,
)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")

MUSIC_SEED = 20260711
MENU_BPM = 90

C5, E5, G5, G4, A2 = 72, 76, 79, 67, 45


def out(directory, filename, samples):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    write_wav(path, samples)
    print(f"wrote {path} ({len(samples) / 22050:.2f}s)")


# ------------------------------------------------------------------- music
GAME_SECTIONS = [
    SectionSpec(progression="Am F C G", bass_style="octave", drum_style="sparse",
                lead_voice="triangle", rest_density=0.3, seed=11, fills=False),
    SectionSpec(progression="Am G F G", bass_style="fifth", drum_style="basic",
                lead_voice="square", rest_density=0.24, seed=22),
    SectionSpec(progression="Am Dm C G", bass_style="octave", drum_style="basic",
                lead_voice="square", rest_density=0.24, seed=33),
    SectionSpec(progression="F G Am", bass_style="climb", drum_style="drive",
                lead_voice="square", shimmer=True, rest_density=0.18, seed=44),
    SectionSpec(progression="Am G F G", bass_style="octave", drum_style="basic",
                lead_voice="thin square", rest_density=0.22, seed=55),
    SectionSpec(progression="Am F C G", bass_style="fifth", drum_style="drive",
                lead_voice="square", shimmer=True, rest_density=0.18, seed=66),
    SectionSpec(progression="Am Dm Am G", bass_style="climb", drum_style="drive",
                lead_voice="square", shimmer=True, rest_density=0.16, seed=77),
    SectionSpec(progression="Am Dm C G", bass_style="octave", drum_style="sparse",
                lead_voice="triangle", rest_density=0.32, seed=88, fills=False),
]

BOSS_SECTIONS = [
    SectionSpec(progression="Am Ab (boss)", bass_style="pulse",
                drum_style="intense", lead_voice="square", shimmer=True,
                rest_density=0.12, seed=101),
    SectionSpec(progression="Am Dm Am G", bass_style="pulse",
                drum_style="intense", lead_voice="thin square", shimmer=True,
                rest_density=0.12, seed=102),
    SectionSpec(progression="Am Ab (boss)", bass_style="octave",
                drum_style="intense", lead_voice="square", shimmer=True,
                rest_density=0.1, seed=103),
]


def build_menu_section(rng, bars=4):
    """Calm arpeggio variant (not SectionSpec-shaped: no drums, slow)."""
    eighth = 60 / MENU_BPM / 2
    progression = rng.choice(list(PROGRESSIONS.values())[:4])
    seq = []
    for bar in range(bars * 2):
        root, is_minor = progression[bar % len(progression)]
        tones = chord_tones(root, is_minor, base=45)
        pattern = rng.choice([
            [0, 1, 2, "8", 2, 1],
            [0, 2, 1, 2, "8", 2],
            [0, 1, "8", 1, 2, 1],
        ])
        for p in pattern[:4]:
            seq.append(tones[0] + 12 if p == "8" else tones[p])
    pad = note_track(seq, eighth, 0.11, decay_power=1.2, triangle=True)
    shimmer = note_track([m + 24 for m in seq], eighth, 0.028, duty=0.3,
                         decay_power=1.0)
    return envelope(mix(pad, shimmer), attack=0.002, release=0.002)


# --------------------------------------------------------------------- sfx
def build_sfx():
    sfx = {}
    sfx["shoot.wav"] = envelope(sweep(1200, 500, 0.12))
    sfx["explosion_enemy.wav"] = envelope(noise(0.18), attack=0.01, release=0.6)
    sfx["explosion_player.wav"] = envelope(
        concat(noise(0.25), sweep(300, 60, 0.25)), attack=0.01, release=0.4)
    sfx["explosion_big.wav"] = envelope(
        mix(noise(0.9, 0.4), sweep(220, 30, 0.9, 0.3)), attack=0.005, release=0.5)

    for i, f in enumerate([220, 196, 175, 165]):
        sfx[f"step_{i}.wav"] = envelope(
            square_wave(f, 0.08), attack=0.005, release=0.05)

    sfx["graze.wav"] = envelope(sweep(2100, 2600, 0.045, 0.18),
                                attack=0.1, release=0.3)
    sfx["powerup.wav"] = envelope(concat(
        square_wave(midi(C5), 0.07, 0.3),
        square_wave(midi(E5), 0.07, 0.3),
        square_wave(midi(G5), 0.12, 0.3),
    ), attack=0.01, release=0.2)
    sfx["shield_break.wav"] = envelope(
        mix(noise(0.3, 0.25, seed=4242), sweep(900, 200, 0.3, 0.2)),
        attack=0.005, release=0.4)
    sfx["boss_roar.wav"] = envelope(
        mix(sweep(90, 42, 1.1, 0.4, duty=0.3), noise(1.1, 0.12, seed=666)),
        attack=0.05, release=0.35)
    sfx["phase_sting.wav"] = envelope(concat(
        mix(square_wave(midi(A2), 0.16, 0.25), square_wave(midi(A2 + 6), 0.16, 0.2)),
        mix(square_wave(midi(A2 - 2), 0.3, 0.25), square_wave(midi(A2 + 4), 0.3, 0.2)),
    ), attack=0.01, release=0.3)
    sfx["toast.wav"] = envelope(concat(
        square_wave(midi(G4), 0.09, 0.28),
        square_wave(midi(C5), 0.09, 0.28),
        square_wave(midi(E5), 0.09, 0.28),
        square_wave(midi(G5), 0.2, 0.28),
    ), attack=0.01, release=0.25)
    sfx["menu_move.wav"] = envelope(square_wave(660, 0.045, 0.2),
                                    attack=0.05, release=0.3)
    sfx["menu_select.wav"] = envelope(concat(
        square_wave(880, 0.06, 0.25), square_wave(1320, 0.09, 0.25)),
        attack=0.02, release=0.25)
    sfx["game_over.wav"] = envelope(concat(
        square_wave(392, 0.15), square_wave(330, 0.15),
        square_wave(262, 0.15), square_wave(196, 0.35),
    ), attack=0.01, release=0.2)
    sfx["win.wav"] = envelope(concat(
        square_wave(523, 0.12), square_wave(659, 0.12),
        square_wave(784, 0.12), square_wave(1047, 0.3),
    ), attack=0.01, release=0.2)
    return sfx


def main():
    for name, samples in build_sfx().items():
        out(SFX_DIR, name, samples)

    for i, spec in enumerate(GAME_SECTIONS):
        out(MUSIC_DIR, f"game_{i:02d}.wav", build_section(spec))
    for i, spec in enumerate(BOSS_SECTIONS):
        out(MUSIC_DIR, f"boss_{i:02d}.wav", build_section(spec))
    rng = random.Random(MUSIC_SEED)
    for i in range(4):
        out(MUSIC_DIR, f"menu_{i:02d}.wav", build_menu_section(rng))


if __name__ == "__main__":
    main()
