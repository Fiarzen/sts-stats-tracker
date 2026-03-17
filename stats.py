"""
stats.py
--------
Computes aggregate statistics across a collection of NormalisedRun objects.
All functions are pure: they take runs as input and return stat objects.
No file I/O or side effects.
"""

from collections import defaultdict
from dataclasses import dataclass

from models import CardStat, EncounterStat, NormalisedRun, RelicStat


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

@dataclass
class RunFilter:
    """
    Optional filters to narrow which runs are included in stat calculations.
    None means "no filter applied" for that field.
    """
    character: str | None = None        # e.g. "REGENT"
    min_ascension: int | None = None
    max_ascension: int | None = None
    win_only: bool = False


def filter_runs(runs: list[NormalisedRun], f: RunFilter) -> list[NormalisedRun]:
    result = runs
    if f.character:
        result = [r for r in result if r.character == f.character]
    if f.min_ascension is not None:
        result = [r for r in result if r.ascension >= f.min_ascension]
    if f.max_ascension is not None:
        result = [r for r in result if r.ascension <= f.max_ascension]
    if f.win_only:
        result = [r for r in result if r.win]
    return result


# ---------------------------------------------------------------------------
# Card stats
# ---------------------------------------------------------------------------

def compute_card_stats(
    runs: list[NormalisedRun],
    min_offers: int = 1,
    split_upgrades: bool = False,
) -> list[CardStat]:
    """
    Calculate pick rate and win rate for every card offered across all runs.

    Args:
        runs:           The runs to analyse.
        min_offers:     Exclude cards offered fewer than this many times.
                        Useful for filtering out noise with small samples.
        split_upgrades: If True, treat RAGE and RAGE (upgraded) as separate
                        entries. If False, merge them under the base card id.
    """
    # offered[card_key] = total times offered
    offered: dict[str, int] = defaultdict(int)
    # picked[card_key] = total times picked
    picked: dict[str, int] = defaultdict(int)
    # runs_containing[card_key] = set of run seeds that picked this card
    runs_containing: dict[str, set[str]] = defaultdict(set)
    # wins_containing[card_key] = set of winning run seeds that had this card
    wins_containing: dict[str, set[str]] = defaultdict(set)
    # upgrade_breakdown[card_key][label] = count picked at that upgrade level
    upgrade_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for run in runs:
        # Track which card keys were picked in this run (for win rate)
        picked_in_this_run: set[str] = set()

        for offer in run.card_offers:
            key = _card_key(offer.card_id, offer.upgrade_level, split_upgrades)
            offered[key] += 1
            if offer.was_picked:
                picked[key] += 1
                picked_in_this_run.add(key)
                label = "upgraded" if offer.upgrade_level > 0 else "base"
                upgrade_breakdown[key][label] += 1

        for key in picked_in_this_run:
            runs_containing[key].add(run.seed)
            if run.win:
                wins_containing[key].add(run.seed)

    stats: list[CardStat] = []
    for card_key, total_offered in offered.items():
        if total_offered < min_offers:
            continue

        total_picked = picked[card_key]
        run_count = len(runs_containing[card_key])
        win_count = len(wins_containing[card_key])

        stats.append(CardStat(
            card_id=card_key,
            times_offered=total_offered,
            times_picked=total_picked,
            pick_rate=total_picked / total_offered,
            runs_with_card=run_count,
            wins_with_card=win_count,
            win_rate=win_count / run_count if run_count > 0 else 0.0,
            upgrade_breakdown=dict(upgrade_breakdown[card_key]),
        ))

    return sorted(stats, key=lambda s: s.win_rate, reverse=True)


# ---------------------------------------------------------------------------
# Relic stats
# ---------------------------------------------------------------------------

def compute_relic_stats(
    runs: list[NormalisedRun],
    min_seen: int = 1,
) -> list[RelicStat]:
    """
    Calculate win rate for every relic seen across all runs.

    Args:
        runs:       The runs to analyse.
        min_seen:   Exclude relics seen in fewer than this many runs.
    """
    # Use sets keyed by seed to avoid double-counting multi-relic runs
    runs_with: dict[str, set[str]] = defaultdict(set)
    wins_with: dict[str, set[str]] = defaultdict(set)

    for run in runs:
        seen_in_run: set[str] = {r.relic_id for r in run.relics_acquired}
        for relic_id in seen_in_run:
            runs_with[relic_id].add(run.seed)
            if run.win:
                wins_with[relic_id].add(run.seed)

    stats: list[RelicStat] = []
    for relic_id, run_set in runs_with.items():
        count = len(run_set)
        if count < min_seen:
            continue
        win_count = len(wins_with[relic_id])
        stats.append(RelicStat(
            relic_id=relic_id,
            times_seen=count,
            wins_with_relic=win_count,
            win_rate=win_count / count,
        ))

    return sorted(stats, key=lambda s: s.win_rate, reverse=True)


# ---------------------------------------------------------------------------
# Encounter stats
# ---------------------------------------------------------------------------

def compute_encounter_stats(
    runs: list[NormalisedRun],
    room_types: list[str] | None = None,
    act: int | None = None,
) -> list[EncounterStat]:
    """
    Calculate difficulty metrics for every encounter seen across all runs.

    Args:
        runs:       The runs to analyse.
        room_types: Optional list of room types to include, e.g. ["elite", "boss"].
                    If None, all types are included.
        act:        If provided, only include encounters from this act number.
    """
    appearances: dict[str, int] = defaultdict(int)
    total_damage: dict[str, int] = defaultdict(int)
    total_turns: dict[str, int] = defaultdict(int)
    room_type_map: dict[str, str] = {}
    kill_counts: dict[str, int] = defaultdict(int)

    for run in runs:
        for enc in run.encounters:
            if room_types and enc.room_type not in room_types:
                continue
            if act is not None and enc.act != act:
                continue

            eid = enc.encounter_id
            appearances[eid] += 1
            total_damage[eid] += enc.damage_taken
            total_turns[eid] += enc.turns_taken
            room_type_map[eid] = enc.room_type

            # Check if this encounter killed the player in this run
            if (
                not run.win
                and run.killed_by_encounter
                and run.killed_by_encounter == eid
            ):
                kill_counts[eid] += 1

    stats: list[EncounterStat] = []
    for eid, count in appearances.items():
        kills = kill_counts[eid]
        stats.append(EncounterStat(
            encounter_id=eid,
            room_type=room_type_map[eid],
            appearances=count,
            avg_damage_taken=total_damage[eid] / count,
            avg_turns_taken=total_turns[eid] / count,
            times_killed_player=kills,
            kill_rate=kills / count,
        ))

    return sorted(stats, key=lambda s: s.avg_damage_taken, reverse=True)


# ---------------------------------------------------------------------------
# Summary stats (overview dashboard)
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    total_runs: int
    wins: int
    losses: int
    win_rate: float
    avg_run_time_seconds: float
    most_played_character: str
    runs_per_character: dict[str, int]
    wins_per_character: dict[str, int]


def compute_run_summary(runs: list[NormalisedRun]) -> RunSummary:
    """High-level overview stats across all runs."""
    if not runs:
        return RunSummary(0, 0, 0, 0.0, 0.0, "N/A", {}, {})

    wins = sum(1 for r in runs if r.win)
    runs_per_char: dict[str, int] = defaultdict(int)
    wins_per_char: dict[str, int] = defaultdict(int)

    for run in runs:
        runs_per_char[run.character] += 1
        if run.win:
            wins_per_char[run.character] += 1

    most_played = max(runs_per_char, key=runs_per_char.get)  # type: ignore[arg-type]
    avg_time = sum(r.run_time_seconds for r in runs) / len(runs)

    return RunSummary(
        total_runs=len(runs),
        wins=wins,
        losses=len(runs) - wins,
        win_rate=wins / len(runs),
        avg_run_time_seconds=avg_time,
        most_played_character=most_played,
        runs_per_character=dict(runs_per_char),
        wins_per_character=dict(wins_per_char),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_key(card_id: str, upgrade_level: int, split_upgrades: bool) -> str:
    if split_upgrades and upgrade_level > 0:
        suffix = "+" * upgrade_level
        return f"{card_id}{suffix}"
    return card_id
