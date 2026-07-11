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


def note_track(seq, note_dur, amplitude, duty=0.5, decay_power=2.5):
    """seq: list of midi numbers (or REST); every note lasts note_dur sec."""
    out = []
    for m in seq:
        if m is REST:
            out.extend([0.0] * int(SAMPLE_RATE * note_dur))
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


def build_game_music():
    """Driving 8-bar loop at 150 BPM in A minor."""
    eighth = 60 / 150 / 2  # 0.2s

    # chord roots per bar: Am Am F F C C G G
    bass_roots = [A2, A2, F2, F2, C3, C3, G2, G2]
    bass = []
    for root in bass_roots:
        bass += [root, root + 12, root, root + 12, root, root + 12, root, root + 12]

    lead = [
        # bar 1-2 (Am)
        A4, REST, C5, A4, E5, REST, C5, A4,
        G4, A4, C5, REST, D5, C5, A4, G4,
        # bar 3-4 (F)
        F3 + 12, REST, A4, C5, A4, REST, C5, D5,
        C5, A4, G4, REST, A4, G4, E4, D4,
        # bar 5-6 (C)
        E4, G4, C5, REST, E5, D5, C5, REST,
        G4, C5, E5, REST, D5, C5, G4, E4,
        # bar 7-8 (G)
        D4, G4, D5, REST, G5, REST, D5, C5,
        D5, REST, G4, A4, C5, D5, E5, REST,
    ]

    drums = ("K.h.S.h." * 8)

    track = mix(
        note_track(bass, eighth, 0.16, duty=0.25, decay_power=1.5),
        note_track(lead, eighth, 0.13, duty=0.5, decay_power=2.2),
        drum_track(drums, eighth),
    )
    return envelope(track, attack=0.002, release=0.002)


def build_menu_music():
    """Calm 4-bar arpeggio loop at 90 BPM."""
    eighth = 60 / 90 / 2  # 0.333s
    arps = [
        [A2, E3, A3, C4, E4, C4, A3, E3],   # Am
        [F2, C3, F3, A3, C4, A3, F3, C3],   # F
        [C3, G3, C4, E4, G4, E4, C4, G3],   # C
        [G2, D4 - 12, G3, C4 - 1, D4, C4 - 1, G3, D4 - 12],  # G (B as C4-1)
    ]
    seq = [n for bar in arps for n in bar]
    pad = note_track(seq, eighth, 0.11, duty=0.5, decay_power=1.2)
    shimmer = note_track(
        [m + 12 if m else REST for m in seq], eighth, 0.035, duty=0.3, decay_power=1.0)
    return envelope(mix(pad, shimmer), attack=0.002, release=0.002)


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

    write_wav(MUSIC_DIR, "game_loop.wav", build_game_music())
    write_wav(MUSIC_DIR, "menu_loop.wav", build_menu_music())


if __name__ == "__main__":
    main()
