"""Pixel Invaders Arcade backend: global leaderboards + daily seeds.

A small FastAPI service meant to run in one container on a home box.

Env:
    ARCADE_DB_PATH       sqlite file (default ./arcade.db; compose: /data/arcade.db)
    ARCADE_API_KEY       if set, POSTs require the X-Api-Key header
    ARCADE_CORS_ORIGINS  comma-separated origins for browser reads (default *)
"""
import hashlib
import os
import re
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from server import db
from server.scoreboard import render_scoreboard

API_KEY = os.environ.get("ARCADE_API_KEY", "")
CORS_ORIGINS = [o.strip() for o in
                os.environ.get("ARCADE_CORS_ORIGINS", "*").split(",")]

SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
NAME_RE = re.compile(r"^[A-Z0-9 ]{1,3}$")

app = FastAPI(title="Pixel Invaders Arcade API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ScoreSubmission(BaseModel):
    game: str = Field(..., max_length=32)
    mode: str = Field(..., max_length=32)
    name: str = Field(..., max_length=3)
    score: int = Field(..., ge=0, le=1_000_000_000)
    wave: int | None = Field(None, ge=0, le=100_000)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/v1/scores")
def submit_score(body: ScoreSubmission,
                 x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="bad api key")
    if not SLUG_RE.match(body.game) or not SLUG_RE.match(body.mode):
        raise HTTPException(status_code=422, detail="bad game/mode slug")
    name = body.name.upper().strip() or "???"
    if not NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="initials must be A-Z/0-9")
    row_id, rank = db.insert_score(body.game, body.mode, name, body.score,
                                   body.wave)
    return {"id": row_id, "rank": rank}


@app.get("/api/v1/scores")
def get_scores(game: str = Query(...), mode: str = Query(...),
               limit: int = Query(10, ge=1, le=100)):
    if not SLUG_RE.match(game) or not SLUG_RE.match(mode):
        raise HTTPException(status_code=422, detail="bad game/mode slug")
    return {"game": game, "mode": mode, "scores": db.top_scores(game, mode, limit)}


@app.get("/api/v1/boards")
def get_boards():
    return {"boards": db.boards()}


@app.get("/api/v1/daily")
def get_daily():
    """Deterministic daily seed for future daily-challenge runs."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seed = int.from_bytes(
        hashlib.sha256(f"pixel-invaders:{today}".encode()).digest()[:8], "big")
    return {"date": today, "seed": seed}


@app.get("/scoreboard", response_class=HTMLResponse)
def scoreboard(game: str = Query("voxelhell"), mode: str = Query("campaign"),
               limit: int = Query(10, ge=1, le=50)):
    """Self-contained retro high-score page — iframe it into a website."""
    if not SLUG_RE.match(game) or not SLUG_RE.match(mode):
        raise HTTPException(status_code=422, detail="bad game/mode slug")
    return render_scoreboard(game, mode, db.top_scores(game, mode, limit))
