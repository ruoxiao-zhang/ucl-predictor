# 欧冠推演室 · UCL Simulator

A bilingual (中文 / English) Champions League 2026/27 simulator: per-match predictions (model vs betting market), odds of reaching each round, the live league-phase table and a title-odds trend.

Live page: https://claude.ai/artifact/BV98ZMG31YLif14jMU5nja

| File | Role |
|---|---|
| `teams.json` | The 36 teams: ESPN id, names, pot, pre-season rating `elo0`, ClubElo name candidates, and manual `adjustments` (team, delta, from, until, zh, en) for injuries / transfers. |
| `update.py` | Pulls fixtures, results and DraftKings odds from ESPN's public scoreboard API, the title market from Polymarket, ratings from ClubElo (falls back to its own Elo walk), freezes per-match predictions before kick-off, simulates the season 50,000 times, writes `data.json`. Standard library only. |
| `data.json` | Everything the page shows, plus the history of title odds. |
| `index.html` | The page. Loads `data.json`; re-simulates in the browser when a viewer edits ratings. |

```
python -X utf8 update.py     # refresh data.json
python -m http.server        # preview at http://localhost:8000
```

## Model

Rating gap + 65 home advantage → expected goals `1.38·10^(±d/1050)` → Poisson scores. Imminent games use the market's de-margined 1X2 probabilities (converted to an equivalent rating gap); the rest use the model. Knockouts: seeded play-off pairings (9/10 v 23/24 …), fixed R16 slots, two legs with extra time at 1/3 rate and 50/50 penalties, neutral final.

## Updates

Cloud routine `trig_01E9cZF3nwqVzdwLB1KwyjdA` runs Tue/Wed/Thu 00:00 UTC (08:00 Beijing): reads the working files stored with the published page, runs `update.py`, republishes, and pushes a notification after match nights. The published page is the source of truth for data.

## Known gaps

- League phase only. When the knockout draw happens (late January 2027), `update.py` must start reading real knockout ties instead of simulating them.
- ClubElo's API returned 502 on 2026-10-01; until it works, ratings are the pre-season estimates plus Elo updates from Champions League games only.
- The Poisson model under-predicts draws in lopsided games compared with the market.
