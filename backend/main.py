"""
main.py
-------
FastAPI application. Loads all .run files from the runs/ directory on startup,
then serves stats via a JSON API.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000
"""
import io
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path

from parser import load_run
from stats import (
    RunFilter, filter_runs,
    compute_card_stats, compute_relic_stats,
    compute_encounter_stats, compute_run_summary,
)

app = FastAPI(title="STS2 Run Analyser")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ── Helper ───────────────────────────────────────────────────────

async def parse_uploads(files: list[UploadFile]) -> list:
    runs = []
    for upload in files:
        try:
            contents = await upload.read()
            # load_run accepts a path; patch parser to also accept bytes
            run = load_run(io.BytesIO(contents))
            runs.append(run)
        except Exception as exc:
            print(f"[WARN] Could not parse {upload.filename}: {exc}")
    return runs


def apply_filters(runs, character, min_ascension, max_ascension, win_only):
    return filter_runs(runs, RunFilter(
        character=character,
        min_ascension=min_ascension,
        max_ascension=max_ascension,
        win_only=win_only,
    ))


# ── Endpoints ────────────────────────────────────────────────────

@app.post("/api/summary")
async def get_summary(
    files: list[UploadFile] = File(...),
    character:     Optional[str] = Query(None),
    min_ascension: Optional[int] = Query(None),
    max_ascension: Optional[int] = Query(None),
    win_only:      bool          = Query(False),
):
    runs = apply_filters(await parse_uploads(files), character, min_ascension, max_ascension, win_only)
    s = compute_run_summary(runs)
    return {
        "total_runs": s.total_runs, "wins": s.wins, "losses": s.losses,
        "win_rate": round(s.win_rate, 4),
        "avg_run_time_seconds": round(s.avg_run_time_seconds),
        "most_played_character": s.most_played_character,
        "runs_per_character": s.runs_per_character,
        "wins_per_character": s.wins_per_character,
    }


@app.post("/api/cards")
async def get_cards(
    files: list[UploadFile] = File(...),
    character:      Optional[str] = Query(None),
    min_ascension:  Optional[int] = Query(None),
    max_ascension:  Optional[int] = Query(None),
    win_only:       bool          = Query(False),
    min_offers:     int           = Query(1),
    split_upgrades: bool          = Query(False),
    sort_by:        str           = Query("win_rate"),
):
    runs = apply_filters(await parse_uploads(files), character, min_ascension, max_ascension, win_only)
    stats = compute_card_stats(runs, min_offers=min_offers, split_upgrades=split_upgrades)
    sort_map = {
        "win_rate":      lambda s: s.win_rate,
        "pick_rate":     lambda s: s.pick_rate,
        "times_offered": lambda s: s.times_offered,
    }
    if sort_by in sort_map:
        stats = sorted(stats, key=sort_map[sort_by], reverse=True)
    return [{"card_id": s.card_id, "times_offered": s.times_offered,
             "times_picked": s.times_picked, "pick_rate": round(s.pick_rate, 4),
             "runs_with_card": s.runs_with_card, "wins_with_card": s.wins_with_card,
             "win_rate": round(s.win_rate, 4), "upgrade_breakdown": s.upgrade_breakdown}
            for s in stats]


@app.post("/api/relics")
async def get_relics(
    files: list[UploadFile] = File(...),
    character:     Optional[str] = Query(None),
    min_ascension: Optional[int] = Query(None),
    max_ascension: Optional[int] = Query(None),
    win_only:      bool          = Query(False),
    min_seen:      int           = Query(1),
    sort_by:       str           = Query("win_rate"),
):
    runs = apply_filters(await parse_uploads(files), character, min_ascension, max_ascension, win_only)
    stats = compute_relic_stats(runs, min_seen=min_seen)
    if sort_by == "times_seen":
        stats = sorted(stats, key=lambda s: s.times_seen, reverse=True)
    return [{"relic_id": s.relic_id, "times_seen": s.times_seen,
             "wins_with_relic": s.wins_with_relic, "win_rate": round(s.win_rate, 4)}
            for s in stats]


@app.post("/api/encounters")
async def get_encounters(
    files: list[UploadFile] = File(...),
    character:     Optional[str]       = Query(None),
    min_ascension: Optional[int]       = Query(None),
    max_ascension: Optional[int]       = Query(None),
    win_only:      bool                = Query(False),
    act:           Optional[int]       = Query(None),
    room_types:    Optional[list[str]] = Query(None),
    sort_by:       str                 = Query("avg_damage"),
):
    runs = apply_filters(await parse_uploads(files), character, min_ascension, max_ascension, win_only)
    stats = compute_encounter_stats(runs, room_types=room_types, act=act)
    sort_map = {
        "avg_damage":  lambda s: s.avg_damage_taken,
        "avg_turns":   lambda s: s.avg_turns_taken,
        "kill_rate":   lambda s: s.kill_rate,
        "appearances": lambda s: s.appearances,
    }
    if sort_by in sort_map:
        stats = sorted(stats, key=sort_map[sort_by], reverse=True)
    return [{"encounter_id": s.encounter_id, "room_type": s.room_type,
             "appearances": s.appearances, "avg_damage_taken": round(s.avg_damage_taken, 1),
             "avg_turns_taken": round(s.avg_turns_taken, 1),
             "times_killed_player": s.times_killed_player, "kill_rate": round(s.kill_rate, 4)}
            for s in stats]


@app.post("/api/characters")
async def get_characters(files: list[UploadFile] = File(...)):
    runs = await parse_uploads(files)
    return sorted({r.character for r in runs})


# ── Frontend ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))