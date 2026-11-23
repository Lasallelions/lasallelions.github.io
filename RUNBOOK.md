# Daily update runbook (Lions LaSalle stats site)

The site at https://lasallelions.github.io/ is `index.html` in this repo, built from `data/*.csv` by `tools/build.py`.
The same data also feeds Claudio's Claude dashboard (artifact store URL `https://claude.ai/artifact/H8ucE5c8gNWroCxJtTQHdT`).
Source: the league's public Spordle pages (Ligue de hockey du Grand Montréal, Junior C). Spordle only renders in a real
browser, so the scraping step uses the built-in browser pane on Claudio's computer (`mcp__remote-devices__Claude_Browser__*`).

All paths below are relative to the repo root. Use today's date in America/Toronto as TODAY (YYYY-MM-DD).

## 1. Plan
`python3 tools/plan.py --today TODAY` prints a JSON list of Spordle game ids to check. If it's empty, skip to step 4 (standings) anyway.

## 2. Scrape (browser pane)
1. Open `https://page.spordle.com/fr/ligue-hockey-grand-montreal/schedule/940231` with `preview_start`. A "Vercel Security Checkpoint" (HTTP 429)
   page clears by itself in a few seconds; wait ~5 s. If a tool says the site isn't allowed, call `request_access` for `https://page.spordle.com`.
2. Run the whole content of `tools/grab.js` with `javascript_tool` (it defines `__grab`, `__scan`, `__status`, `__export`, `__table`).
3. Run `window.__scan(IDS)` with the list from step 1. Then call `await __sleep(40000); __status()` repeatedly until `done` is true
   (about 4–8 s per game; each call must return within 45 s).
4. Run `__export()` and save the returned string exactly as-is to `/tmp/scraped.json` (Write tool). If it's very long, export in
   chunks with `__export([ids...])` and merge the JSON lists into one file.
5. Run `await __table('standings')` and save the result to `/tmp/standings.txt`; `await __table('suspensions')` → `/tmp/suspensions.txt`.
   If either returns `TIMEOUT`, retry once; if still failing, run update.py without that flag.

## 3. Merge
`python3 tools/update.py --games /tmp/scraped.json --standings /tmp/standings.txt --suspensions /tmp/suspensions.txt --today TODAY`
It prints what it added. Games are merged once only (data/state.json), so re-running is safe.
Read the output: `note:` lines comparing sheet goals with the standings are expected for games without a posted sheet.

## 4. Build and publish the website
1. `python3 tools/build.py --today TODAY`
2. Optional check: open `index.html` with Playwright (Chromium is installed; d3 loads from cdnjs) and confirm no page errors.
3. `git add -A && git commit -m "Daily update TODAY" && git -c push.negotiate=true push origin HEAD:main`
   (end the commit message with the attribution lines the session asks for). GitHub Pages republishes within a minute or two.

## 5. Update the Claude dashboard (same data)
Artifact store URL: `https://claude.ai/artifact/H8ucE5c8gNWroCxJtTQHdT` (Dashboard type; read it first with the Artifact tool, `action: "read"`).
For every data file that changed in this run (`git diff --name-only HEAD~1 -- data/`), using the dataset ids in `DATASETS` in tools/build.py:
1. Upload the CSV: Artifact tool, `action: "publish"`, `url` = the store URL, `asset: true`, `file_path` = the CSV (one call per CSV).
2. `ArtifactData` `get` collection `datasets`, doc = dataset id → note `version`.
3. In one `ArtifactData` `batch`: `update` each dataset with `source: {url: <new /_blob/ url>, name: <file name>}`,
   `updated: {at: <UTC now>, by: "Claude"}`, `edit: {via: "claude", at: <UTC now>}`, pinned with `if_version`.
   Also `update` collection `files`, doc `index.html` with `{text: <contents of build/dashboard_index.html>, edit: {...}}`
   (read its version first). Use `file_path` with a JSON file `{"text": ..., "edit": ...}` for the page.
4. Read `data/users/me` doc `check`; it should reach `passed`. If no one has the dashboard open it may stay `checking` — that's fine.
If this step fails, the website is still updated; say so in the summary.

## 6. Report
Send a short summary: Lions games added (score, scorers), other league games added, standings position, anything that failed or looks off.
If nothing was played since the last run, say "No new games" and still publish the refreshed standings.

## Rules
- Never edit `data/*.csv` by hand except for a correction Claudio asks for; record it in `data/state.json` `corrections`.
- Correction already applied: game 7075, Giacomo Mazzuca's extra assist. It's in the data; don't re-apply.
- Penalty minutes: minor 2, double minor 4, major 5, match 5, misconducts 10 (matches the league's standings).
- Bench staff (no jersey number, not in a lineup) are left out of player tables.
