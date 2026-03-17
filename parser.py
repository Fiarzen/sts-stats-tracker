"""
parser.py
---------
Loads .run files (JSON) produced by Slay the Spire 2 and normalises them
into NormalisedRun objects that the stats engine can work with.
"""

import json
import os
from pathlib import Path
from typing import Any

from models import CardOffer, Encounter, NormalisedRun, RelicAcquired


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_run(filepath: str | Path) -> NormalisedRun:
    """Parse a single .run file and return a NormalisedRun."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return _parse_run(raw)


def load_runs_from_directory(directory: str | Path) -> list[NormalisedRun]:
    """
    Recursively find and parse all .run files in a directory.
    Files that fail to parse are skipped with a warning.
    """
    runs: list[NormalisedRun] = []
    for path in Path(directory).rglob("*.run"):
        try:
            runs.append(load_run(path))
        except Exception as exc:
            print(f"[WARN] Could not parse {path}: {exc}")
    return runs


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------

def _parse_run(raw: dict[str, Any]) -> NormalisedRun:
    character = _extract_character(raw)
    killed_by_encounter = _clean_none_field(raw.get("killed_by_encounter"))
    killed_by_event = _clean_none_field(raw.get("killed_by_event"))

    run = NormalisedRun(
        seed=raw.get("seed", "unknown"),
        win=bool(raw.get("win", False)),
        character=character,
        ascension=raw.get("ascension", 0),
        acts_completed=raw.get("acts", []),
        run_time_seconds=raw.get("run_time", 0),
        killed_by_encounter=killed_by_encounter,
        killed_by_event=killed_by_event,
    )

    map_history: list[list[dict]] = raw.get("map_point_history", [])
    for act_index, act in enumerate(map_history):
        act_number = act_index + 1  # acts are 1-indexed for display
        _parse_act(run, act, act_number)

    return run


# ---------------------------------------------------------------------------
# Act / map-point traversal
# ---------------------------------------------------------------------------

def _parse_act(run: NormalisedRun, act: list[dict], act_number: int) -> None:
    for map_point in act:
        point_type = map_point.get("map_point_type", "unknown")
        rooms = map_point.get("rooms", [])
        player_stats_list = map_point.get("player_stats", [])

        # Encounters come from rooms[]
        for room in rooms:
            encounter = _parse_encounter(room, act_number)
            if encounter:
                run.encounters.append(encounter)

        # Card offers, relic picks, etc. come from player_stats[]
        # There is typically one player_stats entry per map point.
        for player_stats in player_stats_list:
            _parse_player_stats(run, player_stats, point_type, act_number)


# ---------------------------------------------------------------------------
# Encounter parsing
# ---------------------------------------------------------------------------

def _parse_encounter(room: dict, act_number: int) -> Encounter | None:
    room_type = room.get("room_type", "")
    if room_type not in ("monster", "elite", "boss"):
        return None

    model_id = room.get("model_id", "ENCOUNTER.UNKNOWN")
    monster_ids = room.get("monster_ids", [])
    turns_taken = room.get("turns_taken", 0)

    return Encounter(
        encounter_id=model_id,
        room_type=room_type,
        act=act_number,
        damage_taken=0,         # filled in below from player_stats
        turns_taken=turns_taken,
        monster_ids=monster_ids,
    )


# ---------------------------------------------------------------------------
# Player stats parsing
# ---------------------------------------------------------------------------

def _parse_player_stats(
    run: NormalisedRun,
    stats: dict,
    point_type: str,
    act_number: int,
) -> None:
    # --- Damage taken: patch into the last encounter added for this point ---
    damage_taken = stats.get("damage_taken", 0)
    if damage_taken and run.encounters:
        # The most recently added encounter belongs to this map point
        run.encounters[-1].damage_taken = damage_taken

    # --- Card offers ---
    source = _point_type_to_card_source(point_type)
    for offer in stats.get("card_choices", []):
        card_data = offer.get("card", {})
        run.card_offers.append(CardOffer(
            card_id=_strip_prefix(card_data.get("id", "UNKNOWN"), "CARD."),
            was_picked=offer.get("was_picked", False),
            upgrade_level=card_data.get("current_upgrade_level", 0),
            source=source,
            act=act_number,
            floor=card_data.get("floor_added_to_deck") if offer.get("was_picked") else None,
        ))

    # --- Relics acquired ---
    relic_source = _point_type_to_relic_source(point_type)
    for relic in stats.get("relic_choices", []):
        if relic.get("was_picked"):
            run.relics_acquired.append(RelicAcquired(
                relic_id=_strip_prefix(relic.get("choice", "UNKNOWN"), "RELIC."),
                source=relic_source,
                act=act_number,
            ))

    # Ancient choice relics (stored slightly differently)
    for ancient in stats.get("ancient_choice", []):
        if ancient.get("was_chosen"):
            run.relics_acquired.append(RelicAcquired(
                relic_id=_strip_prefix(ancient.get("TextKey", "UNKNOWN"), "RELIC."),
                source="ancient",
                act=act_number,
            ))

    # Bought relics (shop)
    for relic_id in stats.get("bought_relics", []):
        run.relics_acquired.append(RelicAcquired(
            relic_id=_strip_prefix(relic_id, "RELIC."),
            source="shop",
            act=act_number,
        ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_character(raw: dict) -> str:
    players = raw.get("players", [])
    if players:
        char = players[0].get("character", "UNKNOWN")
        return _strip_prefix(char, "CHARACTER.")
    return "UNKNOWN"


def _clean_none_field(value: str | None) -> str | None:
    """Turn 'NONE.NONE' sentinel strings into Python None."""
    if not value or value.upper() in ("NONE", "NONE.NONE", ""):
        return None
    return value


def _strip_prefix(value: str, prefix: str) -> str:
    """Remove a leading prefix like 'CARD.' or 'RELIC.' for cleaner display."""
    return value[len(prefix):] if value.startswith(prefix) else value


def _point_type_to_card_source(point_type: str) -> str:
    mapping = {
        "monster": "combat",
        "elite": "combat",
        "boss": "combat",
        "shop": "shop",
        "unknown": "event",
        "treasure": "treasure",
    }
    return mapping.get(point_type, "unknown")


def _point_type_to_relic_source(point_type: str) -> str:
    mapping = {
        "ancient": "ancient",
        "elite": "elite",
        "boss": "boss",
        "treasure": "treasure",
        "shop": "shop",
        "unknown": "event",
        "rest_site": "rest_site",
    }
    return mapping.get(point_type, "unknown")
