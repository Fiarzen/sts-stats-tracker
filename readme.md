# STS2 Stats Tracker

A tool for parsing and analysing run data from Slay the Spire 2. Reads the `.run` files produced by the game and computes statistics across multiple runs, including card pick rates, relic win rates, and encounter difficulty.



---

## Requirements

- Python 3.11 or later (uses built-in `dataclasses` and type union syntax)
- No third-party dependencies are required for the parser or stats engine

---

## Project Structure

```
sts2-analyzer/
├── backend/
│   ├── models.py          # Dataclasses for normalised run data and stat outputs
│   ├── parser.py          # Loads and normalises .run files
│   ├── stats.py           # Computes aggregate statistics across runs
│   └── test_pipeline.py   # Manual test script for verifying the pipeline
├── runs/                  # Place your .run files here
└── README.md
```

---

## Getting Started

Clone or download the repository, then drop your `.run` files into the `runs/` directory. The game saves these automatically after each run; on Steam they are typically found at:

```
%APPDATA%\SlayTheSpire2\runs\
```

To verify the pipeline is working against a single file, run the test script from the `backend/` directory:

```bash
cd backend
python test_pipeline.py ../runs/your_file.run
```

This will print a summary of the parsed run, followed by card stats, relic stats, and encounter stats.

---

## What It Tracks

**Card statistics**

For every card offered across all loaded runs:

- Times offered and times picked
- Pick rate (picked / offered)
- Win rate (wins in runs where the card was picked / total runs where it was picked)
- Whether the card was at base or upgrade level when offered

**Relic statistics**

For every relic acquired across all loaded runs:

- Number of runs containing the relic
- Win rate in those runs
- Source of the relic (ancient choice, elite drop, shop, treasure room, event)

**Encounter statistics**

For every combat encounter seen across all loaded runs:

- Number of appearances
- Average damage taken
- Average turns to complete
- Kill rate (how often this encounter ended the run)

**Run summary**

- Total runs, wins, losses, and overall win rate
- Average run time
- Breakdown by character

---

## Using the Stats Engine in Code

Load a single run:

```python
from parser import load_run
from stats import compute_card_stats, compute_relic_stats, compute_encounter_stats

run = load_run("runs/example.run")
runs = [run]

card_stats   = compute_card_stats(runs, min_offers=1)
relic_stats  = compute_relic_stats(runs, min_seen=1)
enc_stats    = compute_encounter_stats(runs)
```

Load all runs from a directory:

```python
from parser import load_runs_from_directory

runs = load_runs_from_directory("runs/")
```

Filter runs before computing stats:

```python
from stats import RunFilter, filter_runs, compute_card_stats

f = RunFilter(character="REGENT", min_ascension=10)
filtered = filter_runs(runs, f)
card_stats = compute_card_stats(filtered, min_offers=5)
```

Split upgraded cards into separate entries:

```python
card_stats = compute_card_stats(runs, split_upgrades=True)
# RAGE and RAGE+ will appear as separate rows
```

---

## Notes on Sample Size

Win rate figures are only meaningful once you have enough runs containing a given card or relic. With a small number of runs, every picked card will show either 0% or 100% win rate, which is not useful.

As a rough guide:

- Use `min_offers=5` or higher for card stats once you have 20 or more runs
- Use `min_seen=3` or higher for relic stats

These filters are set low by default so the tool produces output immediately, even with a single run.

---
## To run
cd backend
uvicorn main:app --reload --port 8000
# then open http://localhost:8000

---

