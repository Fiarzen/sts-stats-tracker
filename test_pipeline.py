"""
test_pipeline.py
----------------
Runs the parser and stats engine against a single .run file and prints
a human-readable summary. Run from the backend/ directory:

    python test_pipeline.py ../runs/example.run
"""

import json
import sys
from pathlib import Path

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).parent))

from parser import load_run
from stats import (
    RunFilter,
    compute_card_stats,
    compute_encounter_stats,
    compute_relic_stats,
    compute_run_summary,
    filter_runs,
)


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def run_tests(run_file: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  STS2 Analyser — Test Pipeline")
    print(f"{'='*60}\n")

    # --- Load ---
    run = load_run(run_file)
    runs = [run]  # In production this would be load_runs_from_directory()

    print(f"Loaded run: seed={run.seed}, win={run.win}, "
          f"character={run.character}, ascension={run.ascension}")
    print(f"  Acts completed : {', '.join(run.acts_completed)}")
    print(f"  Run time       : {fmt_time(run.run_time_seconds)}")
    print(f"  Card offers    : {len(run.card_offers)}")
    print(f"  Relics acquired: {len(run.relics_acquired)}")
    print(f"  Encounters     : {len(run.encounters)}\n")

    # --- Summary ---
    summary = compute_run_summary(runs)
    print(f"── Run Summary {'─'*45}")
    print(f"  Total runs : {summary.total_runs}")
    print(f"  Win rate   : {fmt_pct(summary.win_rate)}")
    print(f"  Avg time   : {fmt_time(summary.avg_run_time_seconds)}\n")

    # --- Card stats ---
    card_stats = compute_card_stats(runs, min_offers=1)
    print(f"── Card Stats (top 10 by win rate) {'─'*24}")
    print(f"  {'Card':<30} {'Offered':>7} {'Picked':>7} {'Pick%':>7} {'Win%':>7}")
    print(f"  {'─'*30} {'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    for cs in card_stats[:10]:
        print(
            f"  {cs.card_id:<30} "
            f"{cs.times_offered:>7} "
            f"{cs.times_picked:>7} "
            f"{fmt_pct(cs.pick_rate):>7} "
            f"{fmt_pct(cs.win_rate):>7}"
        )

    # --- Relic stats ---
    relic_stats = compute_relic_stats(runs, min_seen=1)
    print(f"\n── Relic Stats {'─'*44}")
    print(f"  {'Relic':<30} {'Seen':>6} {'Wins':>6} {'Win%':>7} {'Source'}")
    print(f"  {'─'*30} {'─'*6} {'─'*6} {'─'*7} {'─'*10}")
    for rs in relic_stats:
        # Find source for display (from raw run data)
        source = next(
            (r.source for r in run.relics_acquired if r.relic_id == rs.relic_id),
            "?"
        )
        print(
            f"  {rs.relic_id:<30} "
            f"{rs.times_seen:>6} "
            f"{rs.wins_with_relic:>6} "
            f"{fmt_pct(rs.win_rate):>7} "
            f"{source}"
        )

    # --- Encounter stats ---
    enc_stats = compute_encounter_stats(runs)
    print(f"\n── Encounter Stats (by avg damage taken) {'─'*18}")
    print(f"  {'Encounter':<40} {'Type':<8} {'Act':>4} {'Seen':>5} {'Dmg':>6} {'Turns':>6} {'KillR':>7}")
    print(f"  {'─'*40} {'─'*8} {'─'*4} {'─'*5} {'─'*6} {'─'*6} {'─'*7}")

    # Map encounter_id back to act for display (takes first appearance)
    enc_act_map = {e.encounter_id: e.act for e in run.encounters}

    for es in enc_stats:
        act_display = enc_act_map.get(es.encounter_id, "?")
        print(
            f"  {es.encounter_id:<40} "
            f"{es.room_type:<8} "
            f"{act_display!s:>4} "
            f"{es.appearances:>5} "
            f"{es.avg_damage_taken:>6.1f} "
            f"{es.avg_turns_taken:>6.1f} "
            f"{fmt_pct(es.kill_rate):>7}"
        )

    print(f"\n{'='*60}")
    print("  All checks passed ✓")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_pipeline.py <path/to/file.run>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}")
        sys.exit(1)

    run_tests(path)
