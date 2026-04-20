import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from models import NormalisedRun

DB_PATH = Path(__file__).parent.parent / "data" / "runs.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                seed TEXT PRIMARY KEY,
                win INTEGER NOT NULL,
                character TEXT NOT NULL,
                ascension INTEGER NOT NULL,
                run_time_seconds INTEGER NOT NULL,
                killed_by_encounter TEXT,
                killed_by_event TEXT,
                acts_completed TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS card_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_seed TEXT NOT NULL REFERENCES runs(seed) ON DELETE CASCADE,
                card_id TEXT NOT NULL,
                was_picked INTEGER NOT NULL,
                upgrade_level INTEGER NOT NULL,
                source TEXT NOT NULL,
                act INTEGER NOT NULL,
                floor INTEGER
            );

            CREATE TABLE IF NOT EXISTS relics_acquired (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_seed TEXT NOT NULL REFERENCES runs(seed) ON DELETE CASCADE,
                relic_id TEXT NOT NULL,
                source TEXT NOT NULL,
                act INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS encounters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_seed TEXT NOT NULL REFERENCES runs(seed) ON DELETE CASCADE,
                encounter_id TEXT NOT NULL,
                room_type TEXT NOT NULL,
                act INTEGER NOT NULL,
                damage_taken INTEGER NOT NULL,
                turns_taken INTEGER NOT NULL
            );
        """)


def save_run(run: NormalisedRun) -> bool:
    """
    Persist a NormalisedRun to the database.
    Returns True if inserted, False if the seed already existed.
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT seed FROM runs WHERE seed = ?", (run.seed,)
        ).fetchone()

        if existing:
            return False

        conn.execute(
            """INSERT INTO runs
               (seed, win, character, ascension, run_time_seconds,
                killed_by_encounter, killed_by_event, acts_completed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.seed, int(run.win), run.character, run.ascension,
                run.run_time_seconds, run.killed_by_encounter,
                run.killed_by_event, json.dumps(run.acts_completed),
            ),
        )

        conn.executemany(
            """INSERT INTO card_offers
               (run_seed, card_id, was_picked, upgrade_level, source, act, floor)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (run.seed, o.card_id, int(o.was_picked),
                 o.upgrade_level, o.source, o.act, o.floor)
                for o in run.card_offers
            ],
        )

        conn.executemany(
            """INSERT INTO relics_acquired
               (run_seed, relic_id, source, act)
               VALUES (?, ?, ?, ?)""",
            [
                (run.seed, r.relic_id, r.source, r.act)
                for r in run.relics_acquired
            ],
        )

        conn.executemany(
            """INSERT INTO encounters
               (run_seed, encounter_id, room_type, act, damage_taken, turns_taken)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (run.seed, e.encounter_id, e.room_type,
                 e.act, e.damage_taken, e.turns_taken)
                for e in run.encounters
            ],
        )

        return True


def load_all_runs_from_db() -> list[NormalisedRun]:
    """Reconstruct NormalisedRun objects from the database."""
    from models import CardOffer, Encounter, RelicAcquired

    with get_connection() as conn:
        run_rows = conn.execute("SELECT * FROM runs").fetchall()
        if not run_rows:
            return []

        seeds = [r["seed"] for r in run_rows]
        placeholders = ",".join("?" * len(seeds))

        offer_rows = conn.execute(
            f"SELECT * FROM card_offers WHERE run_seed IN ({placeholders})", seeds
        ).fetchall()
        relic_rows = conn.execute(
            f"SELECT * FROM relics_acquired WHERE run_seed IN ({placeholders})", seeds
        ).fetchall()
        enc_rows = conn.execute(
            f"SELECT * FROM encounters WHERE run_seed IN ({placeholders})", seeds
        ).fetchall()

    # Group child rows by seed for efficient lookup
    offers_by_seed: dict[str, list] = {}
    for o in offer_rows:
        offers_by_seed.setdefault(o["run_seed"], []).append(
            CardOffer(o["card_id"], bool(o["was_picked"]), o["upgrade_level"],
                      o["source"], o["act"], o["floor"])
        )

    relics_by_seed: dict[str, list] = {}
    for r in relic_rows:
        relics_by_seed.setdefault(r["run_seed"], []).append(
            RelicAcquired(r["relic_id"], r["source"], r["act"])
        )

    encs_by_seed: dict[str, list] = {}
    for e in enc_rows:
        encs_by_seed.setdefault(e["run_seed"], []).append(
            Encounter(e["encounter_id"], e["room_type"], e["act"],
                      e["damage_taken"], e["turns_taken"], [])
        )

    runs = []
    for row in run_rows:
        seed = row["seed"]
        runs.append(NormalisedRun(
            seed=seed,
            win=bool(row["win"]),
            character=row["character"],
            ascension=row["ascension"],
            acts_completed=json.loads(row["acts_completed"]),
            run_time_seconds=row["run_time_seconds"],
            killed_by_encounter=row["killed_by_encounter"],
            killed_by_event=row["killed_by_event"],
            card_offers=offers_by_seed.get(seed, []),
            relics_acquired=relics_by_seed.get(seed, []),
            encounters=encs_by_seed.get(seed, []),
        ))

    return runs