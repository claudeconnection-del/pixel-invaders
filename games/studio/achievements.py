"""Voxel Studio's achievements."""
from meta.achievements import Achievement

ACHIEVEMENTS = [
    Achievement(
        "first_bake", "First Bake", "Preview a section you composed",
        lambda e, d, life, run: e == "studio_bake",
    ),
    Achievement(
        "arranger", "Arranger", "Build a sequence of 4 sections",
        lambda e, d, life, run: e == "studio_slot_added" and d["count"] >= 4,
        progress=lambda life, run: (run.get("slots", 0), 4),
    ),
    Achievement(
        "resident_composer", "Resident Composer",
        "Export a custom soundtrack to the cabinet",
        lambda e, d, life, run: e == "studio_export",
    ),
]
