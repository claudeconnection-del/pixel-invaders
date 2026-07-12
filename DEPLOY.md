# Deploying the arcade backend on the Ubuntu box

The backend is one container: global leaderboards, the embeddable retro
scoreboard page, daily seeds, and multiplayer sessions. It is designed as a
**LAN-local service** — chomey.org tooling polls it locally; nothing needs to
be exposed through a tunnel. Scores live in a named Docker volume and survive
updates.

## Install with Claude Code (recommended)

Paste the prompt below into Claude (Opus) running in Claude Code **on the
Ubuntu box**. It is self-contained; Claude will ask you for a GitHub PAT
(classic, `read:packages` scope) when it needs one.

```text
Set up the Pixel Invaders arcade backend on this machine as a LAN-local
Docker service. It's a private GHCR image; nothing here should be exposed
beyond the local network (no tunnels, no public ports).

Steps:
1. Verify docker and the docker compose plugin are installed and the daemon
   is running; install them via apt if missing (docker.io + docker-compose-v2
   or Docker's official repo, your call). Make sure my user can run docker.
2. Log docker into ghcr.io as user "claudeconnection-del". Ask me to paste a
   GitHub PAT with the read:packages scope — don't echo it back or store it
   anywhere except docker's credential store.
3. Create ~/arcade/docker-compose.yml with exactly this content:

   services:
     arcade-api:
       image: ghcr.io/claudeconnection-del/pixel-invaders-arcade:latest
       ports:
         - "8000:8000"
       volumes:
         - arcade-data:/data
       environment:
         ARCADE_CORS_ORIGINS: "*"
       restart: unless-stopped
   volumes:
     arcade-data:

4. Run: docker compose pull && docker compose up -d (in ~/arcade).
5. Verify:
   - curl http://localhost:8000/healthz returns {"status":"ok"}
   - POST a test score and read it back:
     curl -X POST http://localhost:8000/api/v1/scores \
       -H 'Content-Type: application/json' \
       -d '{"game":"voxelhell","mode":"campaign","name":"TST","score":123}'
     curl 'http://localhost:8000/api/v1/scores?game=voxelhell&mode=campaign'
   - curl 'http://localhost:8000/scoreboard?game=voxelhell&mode=campaign'
     returns an HTML page containing "VOXEL HELL".
   - docker inspect shows the container healthcheck reporting healthy and
     restart policy unless-stopped.
6. If ufw is active, allow port 8000 from the LAN only (e.g. my RFC1918
   subnet), not from everywhere. If ufw is inactive, leave it alone.
7. Confirm the service survives a reboot path: docker compose restart works
   and the test score is still there afterwards (the volume persisted).
8. Finish by printing, clearly labeled:
   - the box's LAN IP and the base URL (http://<lan-ip>:8000)
   - the update command: cd ~/arcade && docker compose pull && docker compose up -d
   - the two endpoints chomey.org tooling can poll locally:
     /api/v1/scores?game=<id>&mode=<id> (JSON) and /scoreboard?... (HTML)
   - a reminder that game machines set PIXEL_INVADERS_SERVER=http://<lan-ip>:8000
     (or settings.server_url in profile.json)

Don't create any cron jobs or auto-updaters — I update manually. Don't
change any other firewall rules or system settings.
```

## Manual install (reference)

```bash
echo '<PAT>' | docker login ghcr.io -u claudeconnection-del --password-stdin
mkdir -p ~/arcade && cd ~/arcade   # place docker-compose.yml here (see above)
docker compose pull && docker compose up -d
curl http://localhost:8000/healthz
```

## Updating (after every push that touches server/)

CI rebuilds and pushes the image automatically. On the box:

```bash
cd ~/arcade && docker compose pull && docker compose up -d
```

## Point the games at it

On each machine that plays (desktop, MacBook), set once:

```
PIXEL_INVADERS_SERVER=http://<box-lan-ip>:8000
```

(or `settings.server_url` in `profile.json`). The SCORES screens gain a
GLOBAL tab and MULTIPLAYER appears in the menu.

**Playing away from home?** Scores earned offline are queued in a local
outbox and submitted automatically the next time the game can reach the API
— nothing is lost, the global board catches up on reconnection.

## chomey.org integration (local polling)

The site's tooling polls the box locally and bakes results into the page —
no cross-tunnel traffic needed:

- JSON: `GET http://<box>:8000/api/v1/scores?game=voxelhell&mode=campaign`
- Ready-made HTML: `GET http://<box>:8000/scoreboard?game=voxelhell&mode=campaign`
  (iframe-able as-is on the home network)

Valid game/mode pairs: `voxelhell/campaign`, `voxelhell/endless`,
`breaker/arcade`, `serpent/arcade`, `voxeldoom/campaign`, `crisis/arcade`,
`aimtrainer/gridshot`.

## Optional hardening

Set in `docker-compose.yml` (then `docker compose up -d`):

- `ARCADE_API_KEY: "something"` — score/session POSTs require the key; set
  `PIXEL_INVADERS_API_KEY` to the same value on the game machines.
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
