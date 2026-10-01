---
name: ucl-refresh
description: Maintain the 欧冠推演室 / UCL Simulator (C:\Users\lily1\ucl-predictor) — sync working files from the live artifact, run update.py, add injury/transfer rating adjustments, change the model or page, and republish. Use when the user asks to update / 更新 the Champions League (欧冠) prediction site.
---

# Maintain the UCL Simulator

Live page: https://claude.ai/artifact/BV98ZMG31YLif14jMU5nja · Local copy: `C:\Users\lily1\ucl-predictor` (see README.md there).

**The artifact is the source of truth.** Cloud routine `trig_01E9cZF3nwqVzdwLB1KwyjdA` ("UCL simulator – match-night refresh", Tue/Wed/Thu 08:00 Asia/Shanghai) reads the working files out of the artifact, runs `update.py` and republishes. Always sync down first and publish all working files back.

| Published path | Local file |
|---|---|
| (page) | `index.html` |
| `data.json` | `data.json` |
| `src/update.py` | `update.py` |
| `src/teams.json` | `teams.json` |
| `src/index.html.txt` | `index.html` |

## Steps

1. **Sync down.** `Artifact` `read` with just the url, then `read` with `paths` `["data.json","src/update.py","src/teams.json","src/index.html.txt"]`; copy each over its local file.
2. **Change what was asked.**
   - Injury / suspension / transfer: add to `teams.json` `adjustments` an entry `{"team":"ARS","delta":-30,"from":"YYYY-MM-DD","until":"YYYY-MM-DD","zh":"…","en":"…"}` with a dated news source in the reason. Keep deltas modest (a key player ≈ 20–50) and always set `until`.
   - Model or page changes: keep `update.py` and the page's JS model in sync (HFA, BASE, SCALE are written to data.json and read by the page).
3. **Run** `python -X utf8 update.py` (ClubElo timeouts take ~90 s locally; WARN lines for ClubElo are normal). Read every line.
4. **Publish** with `url` above, `file_path` `C:\Users\lily1\ucl-predictor\index.html`, no icon, `files` = `{"data.json": "C:\Users\lily1\ucl-predictor\data.json", "src/update.py": {"from": "C:\Users\lily1\ucl-predictor\update.py", "contentType": "text/plain"}, "src/teams.json": "C:\Users\lily1\ucl-predictor\teams.json", "src/index.html.txt": {"from": "C:\Users\lily1\ucl-predictor\index.html", "contentType": "text/plain"}}`.
5. **Commit** in the local git repo (git lives at `C:\Program Files\Git\cmd`); push if a remote is set. Copy this skill to `skill/SKILL.md` if it changed.
6. **Report** in Chinese: new results, model vs market hit rate, title-odds movers.

## Debugging the routine

`RemoteTrigger` `list_runs` with the trigger id, then `get_run_log`. `connect_rejected` from the proxy means the cloud "Default" environment's network allowlist is missing `site.api.espn.com` or `api.clubelo.com`; the user adds them in claude.ai/code environment settings.

## Before late January 2027

The knockout draw follows the last league matchday (27 Jan). `update.py` only handles the league phase; extend it to read real play-off/knockout ties from ESPN (months 202702–202706) and simulate only what's left.
