# 欧冠推演室 · UCL Simulator

A bilingual (中文 / English) Champions League 2026/27 simulator: per-match predictions (model vs betting market), odds of reaching each round, the live league-phase table and a title-odds trend.

Live page: https://ruoxiao-zhang.github.io/ucl-predictor/ (updated on matchdays by GitHub Actions)

| File | Role |
|---|---|
| `teams.json` | The 36 teams: ESPN id, names, pot, pre-season rating `elo0`, ClubElo name candidates, and manual `adjustments` (team, delta, from, until, zh, en) for injuries / transfers, and `home_adv` for venue-specific home advantage. |
| `update.py` | Pulls fixtures, results and bookmaker odds (DraftKings, sometimes Bet 365) from ESPN's public scoreboard API, the title market from Polymarket, ratings from ClubElo (falls back to its own Elo walk), freezes per-match predictions before kick-off, simulates the season 50,000 times, writes `data.json`. Standard library only. |
| `data.json` | Everything the page shows, plus the history of title odds. |
| `index.html` | The page. Loads `data.json`; re-simulates in the browser when a viewer edits ratings. |

```
python -X utf8 update.py     # refresh data.json
python -m http.server        # preview at http://localhost:8000
```

## Model

Rating gap + 65 home advantage (plus any `home_adv` entry: Bodø/Glimt +30 Sep–Oct / +60 Nov–Mar, from their European home/away record since 2021; Shakhtar −45 while playing home games at Stamford Bridge) → expected goals `1.38·10^(±d/1050)` → Poisson scores. Imminent games use the market's de-margined 1X2 probabilities (converted to an equivalent rating gap); the rest use the model. Knockouts: seeded play-off pairings (9/10 v 23/24 …), fixed R16 slots, two legs with extra time at 1/3 rate and 50/50 penalties, neutral final.

## Scoring

Every match prediction is frozen at kick-off and scored against the result, alongside the de-margined market odds captured at the same time. Hit rates and the Brier score count from matchday 2: matchday 1 was played before the site existed and its predictions were backfilled, so it is shown but not counted.

## Updates

`.github/workflows/refresh.yml` runs `update.py` Tue/Wed/Thu 00:00 UTC (08:00 Beijing) and commits `data.json` as github-actions[bot]; it refuses to commit if ESPN failed or a finished result changed. GitHub Pages redeploys on each push. `main` is the single source of truth.

## Known gaps

- League phase only. When the knockout draw happens (late January 2027), `update.py` must start reading real knockout ties instead of simulating them.
- ClubElo's data API returns 502 for every date (site redesigned, its Fixtures API says "deactivated"); update.py makes one 10-second try per run. Until it works, ratings are the pre-season estimates plus Elo updates from Champions League games only.
- The Poisson model under-predicts draws in lopsided games compared with the market.
