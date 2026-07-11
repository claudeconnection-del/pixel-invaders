"""Synthesizes chiptune-style 8-bit sound effects using only the stdlib
(wave + struct + math) -- no numpy/audio libraries required.

Run with: python tools/gen_sound.py
Regenerates everything under assets/sfx/. Committed output is checked into
git so the game runs without needing this script at runtime.
"""
import math
import os
import struct
import wave

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")
SAMPLE_RATE = 22050
AMPLITUDE = 0.35  # keep it well under clipping, these are harsh waveforms


def square_wave(freq, duration, amplitude=AMPLITUDE, duty=0.5):
    n = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq if freq > 0 else n + 1
    samples = []
    for i in range(n):
        phase = (i % period) / period if period else 0
        samples.append(amplitude if phase < duty else -amplitude)
    return samples


def noise(duration, amplitude=AMPLITUDE, seed=12345):
    n = int(SAMPLE_RATE * duration)
    state = seed
    samples = []
    for _ in range(n):
        # simple xorshift PRNG for deterministic, dependency-free noise
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17)
        state ^= (state << 5) & 0xFFFFFFFF
        val = (state % 2000 - 1000) / 1000.0
        samples.append(val * amplitude)
    return samples


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


def concat(*chunks):
    result = []
    for c in chunks:
        result.extend(c)
    return result


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


def write_wav(filename, samples):
    path = os.path.join(OUT_DIR, filename)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        wf.writeframes(frames)
    print(f"wrote {path} ({len(samples) / SAMPLE_RATE:.2f}s)")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    write_wav("shoot.wav", envelope(sweep(1200, 500, 0.12)))

    write_wav(
        "explosion_enemy.wav",
        envelope(noise(0.18), attack=0.01, release=0.6),
    )

    write_wav(
        "explosion_player.wav",
        envelope(concat(noise(0.25), sweep(300, 60, 0.25)), attack=0.01, release=0.4),
    )

    # Classic 4-note descending invader "step" blips, saved individually so
    # the game can cycle through them and speed the cadence up over time.
    step_freqs = [220, 196, 175, 165]
    for i, f in enumerate(step_freqs):
        write_wav(f"step_{i}.wav", envelope(square_wave(f, 0.08), attack=0.005, release=0.05))

    write_wav(
        "game_over.wav",
        envelope(
            concat(
                square_wave(392, 0.15),
                square_wave(330, 0.15),
                square_wave(262, 0.15),
                square_wave(196, 0.35),
            ),
            attack=0.01,
            release=0.2,
        ),
    )

    write_wav(
        "win.wav",
        envelope(
            concat(
                square_wave(523, 0.12),
                square_wave(659, 0.12),
                square_wave(784, 0.12),
                square_wave(1047, 0.3),
            ),
            attack=0.01,
            release=0.2,
        ),
    )


if __name__ == "__main__":
    main()
