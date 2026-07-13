"""Self-contained retro scoreboard HTML (no external assets, iframe-safe)."""
import html

GAME_TITLES = {
    "voxelhell": "VOXEL HELL",
    "breaker": "VOXEL BREAKER",
    "serpent": "VOXEL SERPENT",
}


def render_scoreboard(game, mode, scores):
    title = GAME_TITLES.get(game, game.upper())
    rows = ""
    for entry in scores:
        wave = f"&nbsp;W{entry['wave']}" if entry.get("wave") else ""
        cls = f"r{entry['rank']}" if entry["rank"] <= 3 else ""
        rows += (
            f"<tr class='{cls}'><td>{entry['rank']}</td>"
            f"<td>{html.escape(entry['name'])}</td>"
            f"<td class='s'>{entry['score']:,}{wave}</td>"
            f"<td class='d'>{html.escape(entry['date'])}</td></tr>\n"
        )
    if not rows:
        rows = "<tr><td colspan='4' class='empty'>NO SCORES YET</td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>{html.escape(title)} — High Scores</title>
<style>
  body {{ background: #0a0a12; color: #8cffaa; margin: 0;
         font-family: "Courier New", monospace; }}
  .wrap {{ max-width: 480px; margin: 0 auto; padding: 18px 12px; }}
  h1 {{ font-size: 20px; text-align: center; letter-spacing: 3px;
        text-shadow: 0 0 12px #4c8; margin: 0 0 2px; }}
  h2 {{ font-size: 12px; text-align: center; color: #889;
        letter-spacing: 5px; margin: 0 0 14px; font-weight: normal; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 15px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #1c1c2c; }}
  td.s {{ text-align: right; color: #eee; }}
  td.d {{ text-align: right; color: #667; font-size: 11px; }}
  tr.r1 td {{ color: #fad25a; text-shadow: 0 0 10px #a83; }}
  tr.r2 td {{ color: #dfe4ee; }}
  tr.r3 td {{ color: #d9a066; }}
  td.empty {{ text-align: center; color: #556; padding: 30px 0; }}
  .foot {{ text-align: center; color: #445; font-size: 10px;
           letter-spacing: 2px; margin-top: 14px; }}
</style></head><body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <h2>{html.escape(mode.upper())} — HIGH SCORES</h2>
  <table>{rows}</table>
  <div class="foot">CABINET MAN</div>
</div>
</body></html>"""
