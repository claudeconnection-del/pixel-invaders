"""Export a recorded run replay to GIF or MP4 (client-side, offscreen).

    python tools/export_replay.py <replay.json> [out] [--mp4] [--full]
                                  [--fps N] [--no-crt]

Defaults to a GIF of the run's last ~24s into exports/. --mp4 needs the
optional imageio-ffmpeg (falls back to GIF with a note). Also used by the
cabinet, which spawns this as a subprocess so it never touches the live
game's GL context.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from meta import replay as replay_mod  # noqa: E402
from render import export as export_mod  # noqa: E402

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "exports")


def main(argv):
    if not argv:
        print("usage: export_replay.py <replay.json> [out] [--mp4] [--full] "
              "[--fps N] [--no-crt]")
        return 2
    replay_path = argv[0]
    flags = [a for a in argv[1:] if a.startswith("--")]
    positional = [a for a in argv[1:] if not a.startswith("--")]

    fmt = "mp4" if "--mp4" in flags else "gif"
    full = "--full" in flags
    crt = "--no-crt" not in flags
    fps = export_mod.DEFAULT_FPS
    for i, a in enumerate(flags):
        if a == "--fps" and i + 1 < len(argv):
            pass  # simple form below
    if "--fps" in argv:
        fps = int(argv[argv.index("--fps") + 1])

    if fmt == "mp4" and not export_mod.mp4_available():
        print("MP4 needs imageio-ffmpeg (pip install imageio-ffmpeg); "
              "falling back to GIF.")
        fmt = "gif"

    data = replay_mod.load(replay_path)
    rep = replay_mod.Replay(data)

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    if positional:
        out_path = positional[0]
    else:
        base = f"{rep.game}_{rep.mode}_{rep.score:07d}"
        out_path = os.path.join(EXPORTS_DIR, f"{base}.{fmt}")

    print(f"exporting {rep.game}/{rep.mode} ({rep.duration:.0f}s, "
          f"{rep.frame_count} frames) -> {out_path}")
    export_mod.export(rep, out_path, fmt=fmt, fps=fps, full=full, crt=crt)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"wrote {out_path} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
