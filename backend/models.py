from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CardOffer:
    card_id: str
    was_picked: bool
    upgrade_level: int          # 0 = base, 1 = upgraded, etc.
    source: str                 # "combat", "shop", "event"
    act: int
    floor: Optional[int]        # floor it was added to deck, if picked


@dataclass
class RelicAcquired:
    relic_id: str
    source: str                 # "ancient", "elite", "treasure", "shop", "event"
    act: int


@dataclass
class Encounter:
    encounter_id: str
    room_type: str              # "monster", "elite", "boss"
    act: int
    damage_taken: int
    turns_taken: int
    monster_ids: list[str]


@dataclass
class NormalisedRun:
    seed: str
    win: bool
    character: str
    ascension: int
    acts_completed: list[str]
    run_time_seconds: int
    killed_by_encounter: Optional[str]  # None if won or abandoned
    killed_by_event: Optional[str]

    card_offers: list[CardOffer] = field(default_factory=list)
    relics_acquired: list[RelicAcquired] = field(default_factory=list)
    encounters: list[Encounter] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stat output types (returned by stats.py)
# ---------------------------------------------------------------------------

@dataclass
class CardStat:
    card_id: str
    times_offered: int
    times_picked: int
    pick_rate: float            # times_picked / times_offered
    runs_with_card: int
    wins_with_card: int
    win_rate: float             # wins_with_card / runs_with_card  (NaN if 0)
    upgrade_breakdown: dict[str, int] = field(default_factory=dict)  # "base"/"upgraded" -> count picked


@dataclass
class RelicStat:
    relic_id: str
    times_seen: int             # runs that contained this relic
    wins_with_relic: int
    win_rate: float


@dataclass
class EncounterStat:
    encounter_id: str
    room_type: str
    appearances: int
    avg_damage_taken: float
    avg_turns_taken: float
    times_killed_player: int    # times this encounter was the run-ender
    kill_rate: float            # times_killed_player / appearances
