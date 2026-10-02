---
name: ucl-refresh
description: Maintain the 欧冠推演室 / UCL Simulator (C:\Users\lily1\ucl-predictor) — pull the repo, run update.py, add injury/transfer rating adjustments, change the model or page, and push so GitHub Pages redeploys. Use when the user asks to update / 更新 the Champions League (欧冠) prediction site.
---

# Maintain the UCL Simulator

Live site: https://ruoxiao-zhang.github.io/ucl-predictor/ (GitHub Pages from `main`, linked from the user's portfolio) · Repo: https://github.com/ruoxiao-zhang/ucl-predictor (public) · Local copy: `C:\Users\lily1\ucl-predictor` (see README.md there).

**GitHub `main` is the single source of truth (since 2026-10-02).** The workflow `.github/workflows/refresh.yml` runs Tue/Wed/Thu 00:00 UTC (08:00 Asia/Shanghai): it runs `update.py`, refuses to commit if ESPN failed or a sanity check fails (a finished result changed, title odds don't sum to 1), and commits `data.json` as github-actions[bot]. Pages redeploys on each push. GitHub emails the user when a run fails.

The old claude.ai artifact (https://claude.ai/artifact/BV98ZMG31YLif14jMU5nja) and its Claude routine `trig_01E9cZF3nwqVzdwLB1KwyjdA` are retired (routine disabled); don't publish there or re-enable it, or the data forks.

## Steps

1. **Sync down.** `git pull` in the project folder (git lives at `C:\Program Files\Git\cmd`). The workflow commits there several times a week.
2. **Change what was asked.**
   - Injury / suspension / transfer: add to `teams.json` `adjustments` an entry `{"team":"ARS","delta":-30,"from":"YYYY-MM-DD","until":"YYYY-MM-DD","zh":"…","en":"…"}` with a dated news source in the reason. Keep deltas modest (a key player ≈ 20–50) and always set `until`.
   - Polymarket title market: event slug is `polymarket_slug` in teams.json; if the market is replaced, find the new slug and update it.
   - Model or page changes: keep `update.py` and the page's JS model in sync (HFA, BASE, SCALE are written to data.json and read by the page).
3. **Run** `python -X utf8 update.py` if the data should reflect the change now (ClubElo WARN lines are normal). Read every line. Or skip it and trigger the workflow after pushing (`workflow_dispatch` on refresh.yml via the GitHub API, token from `git credential fill`; no `gh` CLI here).
4. **Commit and push.** Copy this skill to `skill/SKILL.md` if it changed, `git add -A`, one-line commit message, `git push` (pull --rebase first if rejected). Check https://ruoxiao-zhang.github.io/ucl-predictor/ a minute later.
5. **Report** in Chinese: new results, model vs market hit rate, title-odds movers.

## Debugging the workflow

List runs: `GET /repos/ruoxiao-zhang/ucl-predictor/actions/workflows/refresh.yml/runs`; logs are in the run's jobs. A failed "Stop if ESPN was unavailable" step means ESPN was down or changed its API; a failed "Sanity check" names the match ids whose result changed.

## Before late January 2027

The knockout draw follows the last league matchday (27 Jan). `update.py` only handles the league phase; extend it to read real play-off/knockout ties from ESPN (months 202702–202706) and simulate only what's left.
