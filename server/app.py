"""Pixel Invaders Arcade backend: global leaderboards + daily seeds.

A small FastAPI service meant to run in one container on a home box.

Env:
    ARCADE_DB_PATH       sqlite file (default ./arcade.db; compose: /data/arcade.db)
    ARCADE_API_KEY       if set, POSTs require the X-Api-Key header
    ARCADE_CORS_ORIGINS  comma-separated origins for browser reads (default *)
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

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
PLAYER_RE = re.compile(r"^[A-Z0-9 ]{1,8}$")
CODE_RE = re.compile(r"^[A-Z0-9]{4}$")

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


# ------------------------------------------------------ multiplayer sessions
class SessionCreate(BaseModel):
    game: str = Field(..., max_length=32)
    mode: str = Field(..., max_length=32)
    host: str = Field(..., max_length=8)


class SessionJoin(BaseModel):
    name: str = Field(..., max_length=8)


class SessionScore(BaseModel):
    name: str = Field(..., max_length=8)
    score: int = Field(..., ge=0, le=1_000_000_000)
    wave: int | None = Field(None, ge=0, le=100_000)


def _check_key(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="bad api key")


def _player_name(raw):
    name = raw.upper().strip()
    if not PLAYER_RE.match(name):
        raise HTTPException(status_code=422,
                            detail="player name must be 1-8 chars A-Z/0-9")
    return name


@app.post("/api/v1/sessions")
def create_session(body: SessionCreate,
                   x_api_key: str | None = Header(default=None)):
    """Host an async-multiplayer session: everyone who joins gets the same
    seed and races on the same run."""
    _check_key(x_api_key)
    if not SLUG_RE.match(body.game) or not SLUG_RE.match(body.mode):
        raise HTTPException(status_code=422, detail="bad game/mode slug")
    host = _player_name(body.host)
    seed = int.from_bytes(os.urandom(4), "big")
    code = db.create_session(body.game, body.mode, host, seed)
    return {"code": code, "seed": seed, "game": body.game, "mode": body.mode}


@app.post("/api/v1/sessions/{code}/join")
def join_session(code: str, body: SessionJoin,
                 x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    code = code.upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=422, detail="bad session code")
    name = _player_name(body.name)
    result = db.join_session(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail="no such session")
    if result == "taken":
        raise HTTPException(status_code=409, detail="name already joined")
    return db.get_session(code)


@app.post("/api/v1/sessions/{code}/scores")
def submit_session_score(code: str, body: SessionScore,
                         x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    code = code.upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=422, detail="bad session code")
    name = _player_name(body.name)
    ok = db.submit_session_score(code, name, body.score, body.wave)
    if not ok:
        raise HTTPException(status_code=404, detail="not joined to session")
    return db.get_session(code)


@app.get("/api/v1/sessions/{code}")
def get_session(code: str):
    code = code.upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=422, detail="bad session code")
    session = db.get_session(code)
    if session is None:
        raise HTTPException(status_code=404, detail="no such session")
    return session


# ------------------------------------------------- turn-based board matches
TURN_RE = re.compile(r"^[A-Z0-9 _]{1,16}$")
MAX_STATE_BYTES = 64 * 1024


class MatchCreate(BaseModel):
    game: str = Field(..., max_length=32)
    host: str = Field(..., max_length=8)
    state: Any = None
    turn: str | None = Field(None, max_length=16)


class MatchJoin(BaseModel):
    name: str = Field(..., max_length=8)


class MatchMove(BaseModel):
    name: str = Field(..., max_length=8)
    base_version: int = Field(..., ge=1)
    state: Any = None
    turn: str | None = Field(None, max_length=16)


def _turn(raw):
    if raw is None:
        return None
    t = raw.upper().strip()
    if not TURN_RE.match(t):
        raise HTTPException(status_code=422, detail="bad turn token")
    return t


def _check_state(state):
    try:
        if len(json.dumps(state)) > MAX_STATE_BYTES:
            raise HTTPException(status_code=413, detail="state too large")
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="state not JSON-serialisable")


def _match_code(code):
    code = code.upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=422, detail="bad match code")
    return code


@app.post("/api/v1/matches")
def create_match(body: MatchCreate,
                 x_api_key: str | None = Header(default=None)):
    """Host a turn-based board match. The server relays an opaque state blob;
    the games own the rules. Returns the match with version 1."""
    _check_key(x_api_key)
    if not SLUG_RE.match(body.game):
        raise HTTPException(status_code=422, detail="bad game slug")
    _check_state(body.state)
    host = _player_name(body.host)
    return db.create_match(body.game, host, body.state, _turn(body.turn))


@app.post("/api/v1/matches/{code}/join")
def join_match(code: str, body: MatchJoin,
               x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    code = _match_code(code)
    name = _player_name(body.name)
    result = db.join_match(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail="no such match")
    if result == "taken":
        raise HTTPException(status_code=409, detail="name already joined")
    if result == "full":
        raise HTTPException(status_code=409, detail="match is full")
    return db.get_match(code)


@app.post("/api/v1/matches/{code}/move")
def submit_move(code: str, body: MatchMove,
                x_api_key: str | None = Header(default=None)):
    """Turn- and version-gated move. 403 if not your turn, 409 if someone
    moved first (rebase on the returned version and retry)."""
    _check_key(x_api_key)
    code = _match_code(code)
    _check_state(body.state)
    name = _player_name(body.name)
    status, match = db.submit_move(code, name, body.base_version, body.state,
                                   _turn(body.turn))
    if status == "notfound":
        raise HTTPException(status_code=404, detail="no such match")
    if status == "forbidden":
        raise HTTPException(status_code=403, detail="not your turn")
    if status == "conflict":
        raise HTTPException(status_code=409,
                            detail={"error": "version_conflict",
                                    "version": match["version"]})
    return match


@app.get("/api/v1/matches/{code}")
def get_match(code: str, since: int = Query(-1)):
    code = _match_code(code)
    match = db.get_match(code)
    if match is None:
        raise HTTPException(status_code=404, detail="no such match")
    if since >= 0 and match["version"] <= since:
        return {"code": code, "version": match["version"], "changed": False}
    return match


@app.get("/scoreboard", response_class=HTMLResponse)
def scoreboard(game: str = Query("voxelhell"), mode: str = Query("campaign"),
               limit: int = Query(10, ge=1, le=50)):
    """Self-contained retro high-score page — iframe it into a website."""
    if not SLUG_RE.match(game) or not SLUG_RE.match(mode):
        raise HTTPException(status_code=422, detail="bad game/mode slug")
    return render_scoreboard(game, mode, db.top_scores(game, mode, limit))
