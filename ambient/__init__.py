"""Ambient mode — a calm generative visual + audio screen for the cabinet,
entered automatically on idle (setting-gated) or manually (chrome-free).

- preset: pure data (AmbientPreset), the built-in DEFAULTS, the registry with
  unlock gating, idle routing, and the mood-themed achievement rules. Headless.
- scenes: generative scene renderers (GL, built on the existing primitives).
- mode: the AmbientMode engine tying a preset to render + sound.
"""
