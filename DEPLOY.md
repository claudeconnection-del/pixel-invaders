# Deploying the arcade backend on the Ubuntu box

One container serves everything: global leaderboards, the embeddable
scoreboard page, daily seeds, and multiplayer sessions. Data lives in a
named Docker volume, so updates never lose scores.

## First deploy (one time)

1. **Create a GitHub PAT** (classic) with the `read:packages` scope —
   github.com → Settings → Developer settings → Personal access tokens.

2. **Log Docker into GHCR** on the box:

   ```bash
   echo '<YOUR_PAT>' | docker login ghcr.io -u claudeconnection-del --password-stdin
   ```

3. **Get the compose file** onto the box — either clone the repo or just copy
   [docker-compose.yml](docker-compose.yml):

   ```bash
   mkdir -p ~/arcade && cd ~/arcade
   curl -fsSL -u claudeconnection-del:<YOUR_PAT> \
     https://raw.githubusercontent.com/claudeconnection-del/pixel-invaders/main/docker-compose.yml -o docker-compose.yml
   ```

4. **Start it:**

   ```bash
   docker compose pull && docker compose up -d
   curl http://localhost:8000/healthz     # -> {"status":"ok"}
   ```

5. **Open the port on the LAN** if the box runs a firewall:

   ```bash
   sudo ufw allow 8000/tcp
   ```

## Updating (after every push that touches server/)

CI builds and pushes a fresh image to GHCR automatically. On the box:

```bash
cd ~/arcade && docker compose pull && docker compose up -d
```

## Point the games at it

On each machine that plays (desktop, MacBook), set the server URL once in
`profile.json` (`settings.server_url`) or via env var:

```
PIXEL_INVADERS_SERVER=http://<box-hostname-or-ip>:8000
```

The SCORES screens gain a GLOBAL tab and a MULTIPLAYER entry appears in the
menu. Everything degrades silently if the box is off.

## Embed the scoreboard in chomey.org

```html
<iframe src="http://<box>:8000/scoreboard?game=voxelhell&mode=campaign"
        width="500" height="640" frameborder="0"></iframe>
```

Any game/mode works: `breaker/arcade`, `serpent/arcade`,
`voxeldoom/campaign`, `crisis/arcade`, `aimtrainer/gridshot`,
`voxelhell/endless`. JSON for custom rendering:
`GET /api/v1/scores?game=voxelhell&mode=campaign`.

## Optional hardening

Set in `docker-compose.yml` (then `docker compose up -d`):

- `ARCADE_API_KEY: "something"` — score/session POSTs require the key; set
  `PIXEL_INVADERS_API_KEY` to the same value in the game's environment.
- `ARCADE_CORS_ORIGINS: "https://chomey.org"` — restrict browser reads.

## API quick reference

| Endpoint | What |
|---|---|
| `GET /healthz` | container health |
| `POST /api/v1/scores` | submit a high score |
| `GET /api/v1/scores?game=&mode=` | top N JSON |
| `GET /scoreboard?game=&mode=` | retro HTML board (iframe-able) |
| `GET /api/v1/daily` | deterministic daily seed |
| `POST /api/v1/sessions` | host a multiplayer session (code + seed) |
| `POST /api/v1/sessions/{code}/join` | join by code |
| `POST /api/v1/sessions/{code}/scores` | report your seeded-run score |
| `GET /api/v1/sessions/{code}` | live session standings |
