"""The chiptune composition engine — stdlib only (math/random/wave/struct).

Used by tools/gen_sound.py to bake the shipped music bank AND by the Voxel
Studio cabinet module to generate custom sections live. A SectionSpec fully
describes one musical section; build_section(spec) renders it to samples.
"""
import math
import random
import struct
import wave
from dataclasses import dataclass, asdict, fields

SAMPLE_RATE = 22050
REST = None

# ------------------------------------------------------------- oscillators


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def square_wave(freq, duration, amplitude=0.35, duty=0.5):
    n = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq if freq > 0 else n + 1
    samples = []
    for i in range(n):
        phase = (i % period) / period if period else 0
        samples.append(amplitude if phase < duty else -amplitude)
    return samples


def triangle_wave(freq, duration, amplitude=0.35):
    n = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq
    samples = []
    for i in range(n):
        phase = (i % period) / period
        samples.append(amplitude * (4 * abs(phase - 0.5) - 1))
    return samples


def noise(duration, amplitude=0.35, seed=12345):
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


def sweep(freq_start, freq_end, duration, amplitude=0.35, duty=0.5):
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


# ----------------------------------------------------------------- shaping
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
    n = len(samples)
    return [s * (1 - i / n) ** power for i, s in enumerate(samples)]


def concat(*chunks):
    result = []
    for c in chunks:
        result.extend(c)
    return result


def mix(*tracks):
    length = max(len(t) for t in tracks)
    out = [0.0] * length
    for t in tracks:
        for i, s in enumerate(t):
            out[i] += s
    return out


def write_wav(path, samples):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        wf.writeframes(frames)


# ------------------------------------------------------------------ tracks
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


# ------------------------------------------------------------- music theory
# progressions: semitone offsets from A; chords as (offset, is_minor)
PROGRESSIONS = {
    "Am F C G": [(0, True), (0, True), (-4, False), (-4, False),
                 (3, False), (3, False), (-2, False), (-2, False)],
    "Am G F G": [(0, True), (-2, False), (-4, False), (-2, False)] * 2,
    "Am Dm C G": [(0, True), (0, True), (5, True), (3, False),
                  (-4, False), (-4, False), (-2, False), (-2, False)],
    "F G Am": [(-4, False), (-2, False), (0, True), (0, True)] * 2,
    "Am Ab (boss)": [(0, True), (0, True), (-1, False), (-1, False)] * 2,
    "Am Dm Am G": [(0, True), (5, True), (0, True), (-2, False)] * 2,
    # dark/heavy progressions (metal): phrygian b2, tritones, chromatic drops
    "Phrygian (dark)": [(0, True), (0, True), (1, False), (0, True),
                        (0, True), (-2, False), (1, False), (0, True)],
    "Tritone (evil)": [(0, True), (0, True), (6, False), (0, True)] * 2,
    "Chromatic Doom": [(0, True), (-1, False), (-2, False), (-3, False)] * 2,
}
PROGRESSION_NAMES = list(PROGRESSIONS.keys())

A_MINOR = [0, 2, 3, 5, 7, 8, 10]  # natural minor semitone degrees

BASS_STYLES = {
    "octave": lambda r: [r, r + 12, r, r + 12, r, r + 12, r, r + 12],
    "pulse": lambda r: [r] * 8,
    "fifth": lambda r: [r, r, r + 7, r, r + 12, r, r + 7, r],
    "climb": lambda r: [r, r, r + 3, r + 3, r + 7, r + 7, r + 12, r + 7],
    "chug": lambda r: [r, r, r, r + 7, r, r, r, r + 7],  # palm-mute feel
}
BASS_NAMES = list(BASS_STYLES.keys()) + ["none"]

DRUM_STYLES = {
    "basic": "K.h.S.h.",
    "drive": "K.hhS.hh",
    "sparse": "K...S...",
    "intense": "KKh.S.hK",
    "blast": "KSKSKSKS",   # d-beat / blast feel
    "double": "KKKSKKKS",  # double-kick drive
}
DRUM_NAMES = list(DRUM_STYLES.keys()) + ["none"]
DRUM_FILLS = ["K.h.S.SS", "K.SSS.SS", "K.h.SKSK"]

LEAD_VOICES = {
    # name -> (is_triangle, duty)
    "square": (False, 0.5),
    "thin square": (False, 0.25),
    "reed": (False, 0.125),
    "triangle": (True, 0.5),
}
LEAD_NAMES = list(LEAD_VOICES.keys()) + ["none"]


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
            if rng.random() < 0.06:
                cur = max(60, min(84, cur + rng.choice([-12, 12])))
            seq.append(cur)
    return seq


def gen_bass(progression, bars, style_name):
    style = BASS_STYLES[style_name]
    seq = []
    for bar in range(bars):
        root, _ = progression[bar % len(progression)]
        seq += style(45 + root)  # around A2
    return seq


def gen_drums(rng, bars, style_name, fills=True, fill_every=4):
    base = DRUM_STYLES[style_name]
    out = ""
    for bar in range(bars):
        if fills and fill_every and (bar + 1) % fill_every == 0:
            out += rng.choice(DRUM_FILLS)
        else:
            out += base
    return out


# ------------------------------------------------------------- SectionSpec
@dataclass
class SectionSpec:
    """Everything that defines one musical section."""
    tempo: int = 150                  # BPM
    progression: str = "Am F C G"     # PROGRESSIONS key
    bass_style: str = "octave"        # BASS_NAMES
    drum_style: str = "basic"         # DRUM_NAMES
    fills: bool = True
    lead_voice: str = "square"        # LEAD_NAMES
    shimmer: bool = False             # octave-up echo layer
    bars: int = 8
    seed: int = 1
    rest_density: float = 0.2         # melody rest probability

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    @property
    def duration(self):
        return self.bars * 8 * (60 / self.tempo / 2)


def build_section(spec):
    """Render a SectionSpec to float samples."""
    rng = random.Random(spec.seed)
    eighth = 60 / spec.tempo / 2
    progression = PROGRESSIONS.get(spec.progression,
                                   PROGRESSIONS["Am F C G"])
    layers = []

    if spec.bass_style != "none":
        layers.append(note_track(
            gen_bass(progression, spec.bars, spec.bass_style),
            eighth, 0.16, duty=0.25, decay_power=1.5))

    melody = gen_melody(rng, progression, spec.bars,
                        rest_prob=spec.rest_density)
    if spec.lead_voice != "none":
        is_triangle, duty = LEAD_VOICES[spec.lead_voice]
        layers.append(note_track(melody, eighth, 0.13, duty=duty,
                                 decay_power=2.2, triangle=is_triangle))
    if spec.shimmer:
        layers.append(note_track([m + 12 if m else REST for m in melody],
                                 eighth, 0.04, duty=0.125, decay_power=1.2))
    if spec.drum_style != "none":
        layers.append(drum_track(
            gen_drums(rng, spec.bars, spec.drum_style, fills=spec.fills),
            eighth))

    if not layers:
        layers = [[0.0] * int(SAMPLE_RATE * eighth * 8 * spec.bars)]
    return envelope(mix(*layers), attack=0.002, release=0.002)


def rms_profile(samples, spec, buckets_per_bar=8):
    """Per-eighth-note RMS levels, normalized 0..1 — drives visualizations."""
    eighth = 60 / spec.tempo / 2
    size = max(1, int(SAMPLE_RATE * eighth))
    out = []
    for i in range(0, len(samples), size):
        chunk = samples[i:i + size]
        if not chunk:
            break
        out.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)))
    peak = max(out) if out else 1.0
    return [v / peak for v in out] if peak > 0 else out
