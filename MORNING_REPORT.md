# KickCast — Morning Report

Overnight autonomous session, steps 1–7 of the build order all attempted and committed
(11 commits, `e9c809e`..`e8a72d7`). Everything below is either verified against real data
or explicitly labeled as unavailable/unverified — nothing here is guessed.

**Read §6 before trying to reproduce this from a bare `git clone`**: two of the data
sources (openfootball, martj42/international_results) are gitignored and were already
present in this working directory from before this session — no script in this repo
downloads them. Don't assume a fresh clone "just works" without checking that first.

## 1. What's done and working with real data, per step

**Step 1 — fixtures, tables, predictions, site.** Full stack running end-to-end against
real data: SQLite DB (`kickcast_api/models.py`) populated by `scripts/ingest.py` from
openfootball + football-data.co.uk (domestic) and martj42 results/goalscorers +
UEFA's real Nations League fixture list (international). FastAPI backend
(`/leagues`, `/leagues/{code}/standings`, `/leagues/{code}/fixtures`,
`/leagues/{code}/trophy-odds`, `/teams/{id}`, `/teams/{id}/fixtures`, `/matches/{id}`,
`/matches/{id}/prediction`, `/matches/{id}/live`, `/assistant/ask`, `/awards`,
`/replay/matches` and `/replay/matches/{id}`). Next.js frontend (dark theme, emerald accent) with homepage,
league, team, match, assistant, awards, and replay pages. Verified live throughout the
night by curling both the API and the running `next dev` server, not just by passing
tests — e.g. Arsenal vs Leeds renders a real 64/23/13 home/draw/away prediction with
sane expected goals (1.88 vs 0.71), and Man City's real next league fixture (away at
Liverpool) renders correctly on its team page.

**Step 2 — goal-timing windows (all matches) + goalscorer probabilities (international
only).** Timing windows apply the real 1,503-match StatsBomb shape to every match's
expected goals — works everywhere. Scorer probabilities only for international matches
(real per-player data exists there); domestic leagues honestly report unavailable — see
§3.

**Step 3 — card model.** Team-level yellow/red rate model (home/away split), using
football-data.co.uk's card data (no gaps, any season/league since 2005-06). Beats a
league-average baseline out-of-sample on yellow cards; close to a wash on red-card
log-loss (reds are rare enough that team-specific signal barely helps) — see §4.

**Step 4 — trophy odds.** Monte Carlo (20,000 runs) title/top-4/relegation odds for all
5 domestic leagues, using each league's fitted model + real current standings + real
remaining fixtures. Verified: Man City 60.8% title / 99.3% top-4 in the real 2026-27
Premier League table (matches its actual 15-point, 5-game lead).

**Step 5 — assistant.** DB-only mode (no LLM) works for real today: substring team-name
matching + keyword intent detection, answering from the same six DB tools the Gemini
path would use. Verified live: "When does Arsenal play next?" → real fixture; "What are
the odds Arsenal beats Leeds?" → real 64/23/13 prediction; "What is the capital of
France?" → honest decline, not a fabricated answer.

**Step 6 — awards.** International top-scorers leaderboard from real
`goalscorers.csv` data. Verified: Haaland leads with 14 international goals in the last
365 days, Mbappé 13, Kane 10 — plausible given their real recent form.

**Step 7 — replay.** Historical Replay of 6 real StatsBomb 2015/16 Premier League
matches, full goal/card/substitution timelines with real minutes and players. Verified:
Leicester City 4–2 Sunderland, Jamie Vardy 10', Riyad Mahrez 17' and 24' (pen) — real,
checkable football history from Leicester's title-winning season.

## 2. What's built but waiting on an API key

| Feature | Env var | What it unlocks |
|---|---|---|
| Champions League fixtures/odds | `FOOTBALL_DATA_ORG_API_KEY` | Not implemented at all yet, not just key-gated — see §3 |
| Natural-language assistant + web search grounding | `GEMINI_API_KEY` (+ `GEMINI_DAILY_QUOTA`) | Full NLU instead of DB-only keyword matching; search grounding for anything outside our DB |
| Official highlight video links | `YOUTUBE_API_KEY` (+ `YOUTUBE_DAILY_QUOTA`, `YOUTUBE_OFFICIAL_CHANNELS`) | Attaches a real official-channel video link to an answer |
| Live match center | `API_FOOTBALL_KEY` (+ `API_FOOTBALL_DAILY_QUOTA`) | Near-live scores/events, polled every 3 min into our own DB |

All four are fully coded (client, quota tracking, DB-only/fallback behavior, tests
against mocked responses) and fail closed to an honest "unavailable" when the key is
absent — verified by actually running the server without any keys and checking the
responses stay honest. **None have been exercised against a real live key** (the
Gemini and API-Football clients are written against each SDK/API's documented shapes,
introspected or researched, not guessed — but genuinely untested end-to-end). Test this
for real the first time a key is added, starting with a single manual call before
trusting it in production.

## 3. What's placeholder, replay-only, or skipped, and why

- **Domestic-league player stats** (goalscorer probabilities, Golden Boot): no free,
  keyless source exists. Checked football-data.co.uk and openfootball — neither has
  player-level data. API-Football's free tier has it but needs a key.
- **Ballon d'Or / The Best, Puskás**: need real historical voting/nomination data. No
  free, verified dataset found. Reported `available: false` with the reason, never
  simulated from nothing.
- **Champions League**: not built at all (beyond a `.env.example` note). Fixtures need
  football-data.org, but real odds also need a cross-league team-strength rating, which
  is a separate research task (validating ClubElo's terms of use, or building a rating
  from UEFA competition history) — not just a key. Flagged for you to prioritize.
- **Nations League trophy odds**: skipped. Our fixture data is Matchdays 1-4 of 6, no
  knockout draw yet — simulating a title winner from an incomplete tournament structure
  isn't meaningful. The same `simulate_season()` machinery could do group-stage-only
  odds from MD1-4 if useful later.
- **Live match center depth** (win-probability timeline, next-goal probability,
  corner-scorer estimates): only the score/event polling scaffold is built. These need
  real in-play event data to mean anything, which needs `API_FOOTBALL_KEY`. Also: the
  spec mentioned a "3.3% corner goal base rate from our data" — I did not independently
  verify this number against anything actually computed in this repo, so I did not build
  a feature that states it as fact. If you have the source for that figure, point me at
  it and I'll wire it in properly.
- **API-Football↔KickCast team ID mapping**: the live poller matches fixtures to our
  teams by best-effort substring name matching, not a verified ID crosswalk — building
  a real one needs to see actual API-Football responses, which needs a key.
- **YouTube official channel IDs**: deliberately left empty by default
  (`YOUTUBE_OFFICIAL_CHANNELS`) rather than hardcoding IDs I couldn't verify — a wrong
  guess would silently search the wrong channel, worse than no link at all.
- **Kickoff time-zone assumption**: the frontend converts stored `kickoff` strings to
  the viewer's local time assuming they're UTC — **unverified** against openfootball's
  actual documented convention. Flagged again in §7, please double check.

## 4. Backtest results

**Domestic goals model** (`reports/backtest_openfootball.json`; tuned on 2014-15→2020-21
only, held out on 2021-22→2025-26, pooled across the 5 big-5 leagues; xi=0.0022, l2=2.0):

| Model | Full set (n=8,887) | | | Early season MD1-6 (n=1,452) | | |
|---|---|---|---|---|---|---|
| | Acc | RPS↓ | LogLoss | Acc | RPS↓ | LogLoss |
| Baseline (H/D/A rates) | 43.6% | .2298 | 1.073 | 41.7% | .2294 | 1.085 |
| penaltyblog Dixon-Coles | 52.4% | .2017 | .993 | 52.2% | .1973 | .999 |
| Ours, 1-season warm start | 50.2% | .2089 | 1.017 | 44.0% | .2219 | 1.070 |
| **Ours, full-history warm start** | **52.4%** | **.2009** | **.989** | **52.2%** | **.1947** | **.982** |
| Bookmaker closing odds | 54.3% | .1939 | .967 | 54.1% | .1866 | .954 |

Paired bootstrap 95% CI, full-history RPS improvement over each baseline (positive =
ours better): vs frequency baseline +0.0289 [.0263,.0314] full / +0.0347 [.0289,.0407]
early; vs penaltyblog +0.0008 [.0004,.0012] full / +0.0026 [.0006,.0047] early; **vs
1-season warm start +0.0080 [.0064,.0096] full / +0.0272 [.0213,.0333] early — this is
the headline result: full-history warm start clearly fixes the early-season weakness
flagged in HANDOFF.md.** We lose to bookmaker closing odds (-0.0064 to -0.0071 RPS),
reported honestly rather than hidden.

**International model** (`reports/backtest_international.json`; tuned on 2024-25
competitive matches; friendly_weight=0.5, xi=0.001, l2=0.1): on 2025-26 held-out
(n=695), ours 64.9% accuracy / .1544 RPS vs penaltyblog 64.0% / .1549 vs baseline 45.8%
/ .2358. Ties or narrowly beats penaltyblog on World Cup 2026 and UEFA qualifiers/NL
subsets too.

**Card model** (`reports/backtest_cards.json`; same tune/test split discipline;
xi=0.002, l2=15.0): pooled held-out (n=17,780) — yellow cards MAE 1.089 vs baseline
1.108, Poisson NLL 1.682 vs 1.697 (clear win); red cards MAE 0.174 vs 0.188 (win), NLL
0.326 vs 0.326 (a wash — reds are rare enough, ~0.15-0.2/team/match, that team-specific
signal barely beats the league average).

**Cross-source validation**: openfootball vs football-data.co.uk agree on 23,560 of
23,562 overlapping matches (99.99%); the 2 disagreements are plausible
awarded/abandoned-match discrepancies, both shown in `reports/crosscheck_sources.json`,
not hidden.

## 5. Exact counts (queried from the real DB just now)

- **67,609 matches** total (65,881 finished, 1,728 scheduled).
- **539 teams.**
- **5 domestic leagues** (Premier League, La Liga, Serie A, Bundesliga, Ligue 1), each
  **22 seasons** (2005-06 → 2026-27): en.1 8,426 matches, es.1 8,995, it.1 8,859,
  de.1 7,344, fr.1 8,396.
- **International**: 25,589 matches, 2000 → 2026-27, including the **104 real UEFA
  Nations League 2026/27 Matchday 1-4 fixtures**.
- **38,273 match_stats rows** (shots/corners/fouls/cards/closing-odds from
  football-data.co.uk).
- **28,712 goalscorer rows** (martj42, international-only real player names/minutes -
  no domestic-league player data exists in the DB at all, per §3).
- **6 Historical Replay matches**, real StatsBomb 2015/16 Premier League events.
- Frontend: **9 routes** (`/`, `/leagues/[code]`, `/teams/[id]`, `/matches/[id]`,
  `/assistant`, `/awards`, `/replay`, `/replay/[id]`, plus the layout/nav).
- **80 backend tests**, all passing; ruff and mypy clean across 45 source files;
  frontend `next lint` and `next build` (which type-checks) both clean.

## 6. How to run the site locally

From a clean checkout:

```bash
# Backend
cd kickcast
python3.11 -m venv .venv && source .venv/bin/activate   # needs Python >=3.10; project was built/tested on 3.11
pip install -e ".[dev]"

# Data: football-data.co.uk downloads via a script (idempotent, skips already-downloaded
# files); openfootball and martj42/international_results do NOT - no script in this repo
# fetches them; they must already be sitting in data/ (data/openfootball_raw/,
# data/results.csv, data/goalscorers.csv, data/uefa_teams.json). Those three data/ paths
# are gitignored and were already present in this working directory before this session
# - if you're starting from a genuinely bare clone, get them yourself first:
#   - openfootball (CC0): https://github.com/openfootball/football.json -> data/openfootball_raw/
#   - martj42/international_results (CC0): https://github.com/martj42/international_results
#     -> results.csv, goalscorers.csv into data/
# data/nations_league_2026_27_md1_4.json and data/uefa_teams.json were hand-authored
# earlier in this project's history (see HANDOFF.md) - not fetchable by script at all.
python scripts/fetch_footballdata_uk.py

python scripts/ingest.py        # builds/updates data/kickcast.db, ~15s, idempotent
uvicorn kickcast_api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000 by default
npm run dev                     # http://localhost:3000

# Verify
pytest                                                            # 80 passed
ruff check .                                                      # clean
mypy kickcast_engine kickcast_api --ignore-missing-imports        # clean
cd frontend && npm run lint && npm run build                      # clean
```

To add any of the 4 optional keys, copy `.env.example` to `.env` at the repo root and
fill in what you have; the site works fully without any of them.

## 7. Judgment calls / things to double-check

1. **Repo-integrity bug fixed first thing**: `.gitignore`'s bare `data/` pattern had
   been silently excluding `kickcast_engine/data/` (the openfootball/statsbomb/
   international loaders) from git since it was written — HANDOFF.md called that module
   "tested, do not throw away," but a fresh clone would have been missing it entirely.
   Scoped the pattern to `/data/`. Also added the `[build-system]`/`[tool.setuptools]`
   table `pyproject.toml` was missing, without which `pip install -e ".[dev]"` failed
   outright.
2. **DB schema** (`kickcast_api/models.py`) wasn't specified in the brief — I designed
   it: natural-key upsert on `(league_code, date, home_team_id, away_team_id)` for
   idempotent ingestion, provenance (`source`/`source_id`) on every match, a shared
   canonical team-ID scheme (`kickcast_engine/data/team_aliases.py`) across openfootball
   and football-data.co.uk. Worth a look before treating it as fixed.
3. **Kickoff time-zone**: flagged in §3 — the "viewer's local time" conversion assumes
   stored kickoff strings are UTC, unverified.
4. **Model caching**: each competition's fitted model is cached in memory, keyed by
   `(db URL, namespace, league_code, data_version)`, refit only when `scripts/ingest.py`
   bumps `data_version` — not a scheduled background refresh. If you run the site for
   a long stretch without re-ingesting, predictions stay pinned to the last ingest.
5. **International team IDs** are a simple slug of the country name (`_slugify` in
   `scripts/ingest.py`), separate from the domestic `team_aliases.py` canonicalization -
   two different ID schemes by design (countries aren't clubs), but worth knowing.
6. **Assistant DB-fallback caching**: only Gemini-sourced answers are cached (to save
   quota); DB-fallback answers are recomputed every time (cheap, and avoids staleness).
   Cache has no expiry yet - a genuinely stale cached Gemini answer would persist
   indefinitely; fine for now, worth a TTL later if this matters to you.
7. **Card model complexity**: deliberately simpler than the goals model (empirical-Bayes
   shrinkage, not a full MLE fit) — cards are mostly about a team's own discipline, not
   an attack/defence interaction with the opponent. Documented as a judgment call in
   `kickcast_engine/models/cards.py`, not hidden.
8. **Everything in §2 and §3** is effectively a list of things I decided to leave
   unbuilt or partially built rather than fake — please skim both before assuming a
   feature is further along than it is.

Nothing was deployed, no accounts were created, no money was spent. Working tree is
clean; every step above is its own commit (`git log --oneline` from `e9c809e` through
this file's commit) so you can review incrementally.
