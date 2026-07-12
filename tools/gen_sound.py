"""Synthesizes all chiptune sound effects AND music using only the stdlib
(wave + struct + math) -- no numpy/audio libraries required.

Run with: python tools/gen_sound.py
Regenerates everything under assets/sfx/ and assets/music/.
"""
import math
import os
import struct
import wave

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")
SAMPLE_RATE = 22050
AMPLITUDE = 0.35


# ----------------------------------------------------------- oscillators
def square_wave(freq, duration, amplitude=AMPLITUDE, duty=0.5):
    n = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq if freq > 0 else n + 1
    samples = []
    for i in range(n):
        phase = (i % period) / period if period else 0
        samples.append(amplitude if phase < duty else -amplitude)
    return samples


def triangle_wave(freq, duration, amplitude=AMPLITUDE):
    n = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq
    samples = []
    for i in range(n):
        phase = (i % period) / period
        samples.append(amplitude * (4 * abs(phase - 0.5) - 1))
    return samples


def noise(duration, amplitude=AMPLITUDE, seed=12345):
    n = int(SAMPLE_RATE * duration)
    state = seed
    samples = []
    for _ in range(n):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17)
        state ^= (state << 5) & 0xFFFFFFFF
        val = (state % 2000 - 1000) / 1000.0
        samples.append(val * amplitude)
    return samples


def sweep(freq_start, freq_end, duration, amplitude=AMPLITUDE, duty=0.5):
    n = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(n):
        t = i / n if n else 0
        freq = freq_start + (freq_end - freq_start) * t
        phase += freq / SAMPLE_RATE
        phase %= 1.0
        samples.append(amplitude if phase < duty else -amplitude)
    return samples


# -------------------------------------------------------------- shaping
def envelope(samples, attack=0.02, release=0.05):
    n = len(samples)
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    out = list(samples)
    for i in range(min(a, n)):
        out[i] *= i / a
    for i in range(min(r, n)):
        out[n - 1 - i] *= i / r
    return out


def decay(samples, power=3.0):
    """Exponential-ish per-note decay for plucky chiptune notes."""
    n = len(samples)
    return [s * (1 - i / n) ** power for i, s in enumerate(samples)]


def concat(*chunks):
    result = []
    for c in chunks:
        result.extend(c)
    return result


def mix(*tracks):
    """Sum tracks of (possibly) different lengths."""
    length = max(len(t) for t in tracks)
    out = [0.0] * length
    for t in tracks:
        for i, s in enumerate(t):
            out[i] += s
    return out


def write_wav(directory, filename, samples):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        wf.writeframes(frames)
    print(f"wrote {path} ({len(samples) / SAMPLE_RATE:.2f}s)")


# ---------------------------------------------------------------- music
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)

# note names for readability: A2=45, C3=48 ... using midi numbers
A1, E2, F2, G2, A2, C3, E3, F3, G3, A3 = 33, 40, 41, 43, 45, 48, 52, 53, 55, 57
C4, D4, E4, G4, A4, C5, D5, E5, G5 = 60, 62, 64, 67, 69, 72, 74, 76, 79
REST = None


def note_track(seq, note_dur, amplitude, duty=0.5, decay_power=2.5,
               triangle=False):
    """seq: list of midi numbers (or REST); every note lasts note_dur sec."""
    out = []
    for m in seq:
        if m is REST:
            out.extend([0.0] * int(SAMPLE_RATE * note_dur))
        elif triangle:
            out.extend(decay(triangle_wave(midi(m), note_dur, amplitude),
                             decay_power))
        else:
            out.extend(decay(square_wave(midi(m), note_dur, amplitude, duty),
                             decay_power))
    return out


def drum_track(pattern, note_dur, kick_amp=0.30, hat_amp=0.05, snare_amp=0.16):
    """pattern chars: K kick, S snare, h hat, . rest — one per 8th note."""
    out = []
    for ch in pattern:
        n = int(SAMPLE_RATE * note_dur)
        if ch == "K":
            hit = decay(sweep(160, 45, note_dur, kick_amp), 4.0)
        elif ch == "S":
            hit = decay(noise(note_dur, snare_amp, seed=777), 4.0)
        elif ch == "h":
            hit = decay(noise(note_dur, hat_amp, seed=333), 8.0)
        else:
            hit = [0.0] * n
        out.extend(hit[:n] + [0.0] * max(0, n - len(hit)))
    return out


# ------------------------------------------------ procedural music sections
# Everything is in A minor at a fixed tempo per pool so any section can
# follow any other; the runtime sequencer (game/assets.py) shuffles them.
# Composition is seeded, so bakes are reproducible.

import random as _random

MUSIC_SEED = 20260711
GAME_BPM = 150
MENU_BPM = 90

# progressions as semitone offsets from A; chords as (offset, is_minor)
PROGRESSIONS = [
    [(0, True), (0, True), (-4, False), (-4, False),
     (3, False), (3, False), (-2, False), (-2, False)],   # Am Am F F C C G G
    [(0, True), (-2, False), (-4, False), (-2, False)] * 2,  # Am G F G
    [(0, True), (0, True), (5, True), (3, False),
     (-4, False), (-4, False), (-2, False), (-2, False)],  # Am Am Dm C F F G G
    [(-4, False), (-2, False), (0, True), (0, True)] * 2,    # F G Am Am
]

BOSS_PROGRESSIONS = [
    [(0, True), (0, True), (-1, False), (-1, False)] * 2,    # Am Am Ab(!) tension
    [(0, True), (5, True), (0, True), (-2, False)] * 2,      # Am Dm Am G
]

A_MINOR = [0, 2, 3, 5, 7, 8, 10]  # natural minor semitone degrees

BASS_STYLES = {
    "octave": lambda r: [r, r + 12, r, r + 12, r, r + 12, r, r + 12],
    "pulse": lambda r: [r] * 8,
    "fifth": lambda r: [r, r, r + 7, r, r + 12, r, r + 7, r],
    "climb": lambda r: [r, r, r + 3, r + 3, r + 7, r + 7, r + 12, r + 7],
}

DRUM_STYLES = {
    "basic": "K.h.S.h.",
    "drive": "K.hhS.hh",
    "sparse": "K...S...",
    "intense": "KKh.S.hK",
}
DRUM_FILLS = ["K.h.S.SS", "K.SSS.SS", "K.h.SKSK"]


def chord_tones(root_offset, is_minor, base=57):  # base A3
    third = 3 if is_minor else 4
    return [base + root_offset, base + root_offset + third,
            base + root_offset + 7]


def gen_melody(rng, progression, bars, rest_prob=0.18):
    """Seeded random walk over A minor, snapping to chord tones on
    downbeats. 8 eighth-notes per bar."""
    seq = []
    cur = 69  # A4
    for bar in range(bars):
        root, is_minor = progression[bar % len(progression)]
        tones = chord_tones(root, is_minor, base=69 + (root < -3) * 12)
        for step in range(8):
            if rng.random() < rest_prob and step % 4 != 0:
                seq.append(REST)
                continue
            if step % 4 == 0:
                cur = rng.choice(tones)
            else:
                move = rng.choice([-2, -1, -1, 1, 1, 2, 3, -3])
                degree = min(range(len(A_MINOR)),
                             key=lambda i: abs((cur % 12) - A_MINOR[i]))
                octave = cur // 12
                degree += move
                octave += degree // len(A_MINOR)
                degree %= len(A_MINOR)
                cur = octave * 12 + A_MINOR[degree]
            cur = max(60, min(84, cur))  # C4..C6
            # occasional octave stab for spice
            if rng.random() < 0.06:
                cur = max(60, min(84, cur + rng.choice([-12, 12])))
            seq.append(cur)
    return seq


def gen_bass(rng, progression, bars, style_name):
    style = BASS_STYLES[style_name]
    seq = []
    for bar in range(bars):
        root, _ = progression[bar % len(progression)]
        seq += style(45 + root)  # around A2
    return seq


def gen_drums(rng, bars, style_name, fill_every=4):
    base = DRUM_STYLES[style_name]
    out = ""
    for bar in range(bars):
        if fill_every and (bar + 1) % fill_every == 0:
            out += rng.choice(DRUM_FILLS)
        else:
            out += base
    return out


def build_game_section(rng, intensity, bars=8):
    """One 8-bar section; intensity 0 (calm) / 1 (mid) / 2 (full)."""
    eighth = 60 / GAME_BPM / 2
    progression = rng.choice(PROGRESSIONS)
    bass_style = rng.choice(["octave", "fifth", "climb"])
    layers = []

    layers.append(note_track(gen_bass(rng, progression, bars, bass_style),
                             eighth, 0.16, duty=0.25, decay_power=1.5))
    melody = gen_melody(rng, progression, bars,
                        rest_prob=0.3 - 0.06 * intensity)
    if intensity == 0:
        layers.append(note_track(melody, eighth, 0.12, decay_power=1.6,
                                 triangle=True))
        layers.append(drum_track(gen_drums(rng, bars, "sparse", fill_every=0),
                                 eighth, hat_amp=0.03))
    elif intensity == 1:
        layers.append(note_track(melody, eighth, 0.13, duty=0.5,
                                 decay_power=2.2))
        layers.append(drum_track(gen_drums(rng, bars, "basic"), eighth))
    else:
        layers.append(note_track(melody, eighth, 0.13, duty=0.5,
                                 decay_power=2.2))
        # shimmer: melody echoed an octave up, thinner voice
        layers.append(note_track([m + 12 if m else REST for m in melody],
                                 eighth, 0.04, duty=0.125, decay_power=1.2))
        layers.append(drum_track(gen_drums(rng, bars, "drive"), eighth))
    return envelope(mix(*layers), attack=0.002, release=0.002)


def build_boss_section(rng, bars=8):
    eighth = 60 / GAME_BPM / 2
    progression = rng.choice(BOSS_PROGRESSIONS)
    melody = gen_melody(rng, progression, bars, rest_prob=0.12)
    layers = [
        note_track(gen_bass(rng, progression, bars, "pulse"), eighth, 0.19,
                   duty=0.25, decay_power=1.2),
        note_track(melody, eighth, 0.13, duty=0.5, decay_power=2.4),
        note_track([m - 12 if m else REST for m in melody], eighth, 0.05,
                   duty=0.25, decay_power=1.5),
        drum_track(gen_drums(rng, bars, "intense", fill_every=2), eighth,
                   kick_amp=0.34, snare_amp=0.2),
    ]
    return envelope(mix(*layers), attack=0.002, release=0.002)


def build_menu_section(rng, bars=4):
    eighth = 60 / MENU_BPM / 2
    progression = rng.choice(PROGRESSIONS)
    seq = []
    for bar in range(bars * 2):  # arps read the progression at double rate
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


def build_music_bank():
    """Bake the section pools the runtime sequencer shuffles through."""
    rng = _random.Random(MUSIC_SEED)
    sections = {}
    intensities = [0, 1, 1, 2, 1, 2, 2, 0]  # varied moods across the pool
    for i, intensity in enumerate(intensities):
        sections[f"game_{i:02d}.wav"] = build_game_section(rng, intensity)
    for i in range(3):
        sections[f"boss_{i:02d}.wav"] = build_boss_section(rng)
    for i in range(4):
        sections[f"menu_{i:02d}.wav"] = build_menu_section(rng)
    return sections


# ------------------------------------------------------------------ main
def main():
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

    sfx["graze.wav"] = envelope(sweep(2100, 2600, 0.045, 0.18), attack=0.1, release=0.3)
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
    sfx["menu_move.wav"] = envelope(square_wave(660, 0.045, 0.2), attack=0.05, release=0.3)
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

    for name, samples in sfx.items():
        write_wav(SFX_DIR, name, samples)

    for filename, samples in build_music_bank().items():
        write_wav(MUSIC_DIR, filename, samples)


if __name__ == "__main__":
    main()
