"""
main.py
-------
FastAPI application. Loads all .run files from the runs/ directory on startup,
then serves stats via a JSON API.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000
"""

import shutil
import tempfile
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, save_run, load_all_runs_from_db
from models import NormalisedRun
from parser import load_run, load_runs_from_directory
from stats import (
    RunFilter,
    compute_card_stats,
    compute_encounter_stats,
    compute_relic_stats,
    compute_run_summary,
    filter_runs,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent.parent
RUNS_DIR   = BASE_DIR / "runs"
FRONTEND_DIR = BASE_DIR / "frontend"

RUNS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory run store — populated on startup, updated on upload
# ---------------------------------------------------------------------------

_runs: list[NormalisedRun] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runs
    init_db()
    _runs = load_all_runs_from_db()
    print(f"Loaded {len(_runs)} run(s) from database")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="STS2 Run Analyser", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://spirestats.netlify.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: build a filtered run list from common query params
# ---------------------------------------------------------------------------

def _get_filtered_runs(
    character: Optional[str],
    min_ascension: Optional[int],
    max_ascension: Optional[int],
    win_only: bool,
) -> list[NormalisedRun]:
    f = RunFilter(
        character=character,
        min_ascension=min_ascension,
        max_ascension=max_ascension,
        win_only=win_only,
    )
    return filter_runs(_runs, f)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/summary")
def get_summary(
    character: Optional[str] = Query(None),
    min_ascension: Optional[int] = Query(None),
    max_ascension: Optional[int] = Query(None),
    win_only: bool = Query(False),
):
    runs = _get_filtered_runs(character, min_ascension, max_ascension, win_only)
    s = compute_run_summary(runs)
    return {
        "total_runs":            s.total_runs,
        "wins":                  s.wins,
        "losses":                s.losses,
        "win_rate":              round(s.win_rate, 4),
        "avg_run_time_seconds":  round(s.avg_run_time_seconds),
        "most_played_character": s.most_played_character,
        "runs_per_character":    s.runs_per_character,
        "wins_per_character":    s.wins_per_character,
    }


@app.get("/api/cards")
def get_cards(
    character:     Optional[str] = Query(None),
    min_ascension: Optional[int] = Query(None),
    max_ascension: Optional[int] = Query(None),
    win_only:      bool          = Query(False),
    min_offers:    int           = Query(1),
    split_upgrades: bool         = Query(False),
    sort_by:       str           = Query("win_rate"),  # win_rate | pick_rate | times_offered
):
    runs = _get_filtered_runs(character, min_ascension, max_ascension, win_only)
    stats = compute_card_stats(runs, min_offers=min_offers, split_upgrades=split_upgrades)

    sort_map = {
        "win_rate":     lambda s: s.win_rate,
        "pick_rate":    lambda s: s.pick_rate,
        "times_offered": lambda s: s.times_offered,
    }
    if sort_by in sort_map:
        stats = sorted(stats, key=sort_map[sort_by], reverse=True)

    return [
        {
            "card_id":         s.card_id,
            "times_offered":   s.times_offered,
            "times_picked":    s.times_picked,
            "pick_rate":       round(s.pick_rate, 4),
            "runs_with_card":  s.runs_with_card,
            "wins_with_card":  s.wins_with_card,
            "win_rate":        round(s.win_rate, 4),
            "upgrade_breakdown": s.upgrade_breakdown,
        }
        for s in stats
    ]


@app.get("/api/relics")
def get_relics(
    character:     Optional[str] = Query(None),
    min_ascension: Optional[int] = Query(None),
    max_ascension: Optional[int] = Query(None),
    win_only:      bool          = Query(False),
    min_seen:      int           = Query(1),
    sort_by:       str           = Query("win_rate"),  # win_rate | times_seen
):
    runs = _get_filtered_runs(character, min_ascension, max_ascension, win_only)
    stats = compute_relic_stats(runs, min_seen=min_seen)

    if sort_by == "times_seen":
        stats = sorted(stats, key=lambda s: s.times_seen, reverse=True)

    return [
        {
            "relic_id":        s.relic_id,
            "times_seen":      s.times_seen,
            "wins_with_relic": s.wins_with_relic,
            "win_rate":        round(s.win_rate, 4),
        }
        for s in stats
    ]


@app.get("/api/encounters")
def get_encounters(
    character:     Optional[str]       = Query(None),
    min_ascension: Optional[int]       = Query(None),
    max_ascension: Optional[int]       = Query(None),
    win_only:      bool                = Query(False),
    act:           Optional[int]       = Query(None),
    room_types:    Optional[list[str]] = Query(None),
    sort_by:       str                 = Query("avg_damage"),  # avg_damage | avg_turns | kill_rate | appearances
):
    runs = _get_filtered_runs(character, min_ascension, max_ascension, win_only)
    stats = compute_encounter_stats(runs, room_types=room_types, act=act)

    sort_map = {
        "avg_damage":  lambda s: s.avg_damage_taken,
        "avg_turns":   lambda s: s.avg_turns_taken,
        "kill_rate":   lambda s: s.kill_rate,
        "appearances": lambda s: s.appearances,
    }
    if sort_by in sort_map:
        stats = sorted(stats, key=sort_map[sort_by], reverse=True)

    return [
        {
            "encounter_id":      s.encounter_id,
            "room_type":         s.room_type,
            "appearances":       s.appearances,
            "avg_damage_taken":  round(s.avg_damage_taken, 1),
            "avg_turns_taken":   round(s.avg_turns_taken, 1),
            "times_killed_player": s.times_killed_player,
            "kill_rate":         round(s.kill_rate, 4),
        }
        for s in stats
    ]


@app.get("/api/characters")
def get_characters():
    """Return all distinct characters seen across loaded runs."""
    return sorted({r.character for r in _runs})


@app.post("/api/upload")
async def upload_runs(files: list[UploadFile] = File(...)):
    global _runs
    results = {"loaded": [], "skipped": [], "failed": []}

    for upload in files:
        try:
            contents = await upload.read()
            run = load_run(io.BytesIO(contents))
            inserted = save_run(run)
            if inserted:
                _runs = [r for r in _runs if r.seed != run.seed] + [run]
                results["loaded"].append(upload.filename)
            else:
                results["skipped"].append(upload.filename)  # duplicate seed
        except Exception as exc:
            results["failed"].append({"file": upload.filename, "reason": str(exc)})

    return results


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(str(index))
