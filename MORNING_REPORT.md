# KickCast — Morning Report

Two sessions layered here: the original overnight run (steps 1–7, commits `e9c809e`..`e8a72d7`,
summarized below) and a second session (this update) where the user added all 4 real API keys
to `.env` and asked for them verified against real calls, Champions League, real domestic
player stats, a real Wikipedia fallback for the assistant, and a specific test question.
13 commits this session, `6898b06`..`15c3d2d`. Everything below is either verified against
real data/real API calls or explicitly labeled as unavailable/unverified — nothing is guessed.
**`.env`'s 4 real key values were never printed, logged, committed, or copied anywhere in this
session** — confirmed clean before starting and re-checked before every commit.

**Read §6 before trying to reproduce this from a bare `git clone`**: two of the data
sources (openfootball, martj42/international_results) are gitignored and were already
present in this working directory from before either session — no script in this repo
downloads them (a `scripts/fetch_open_data.sh` was added since the last report for the
other two open sources, but not these). Don't assume a fresh clone "just works."

## 1. What's done and working with real data, per step/item

**Steps 1–4, 6–7 (prior session)**: full stack (DB, FastAPI, Next.js frontend), goal-timing
windows, card model, domestic trophy odds, international awards leaderboard, StatsBomb
Historical Replay — all still working, re-verified in this session. See §4 for updated
backtest numbers (the historical data was also extended back to 2001-02 this session, see below).

**Domestic history extended to 2001-02** (was 2005-06): 20 more football-data.co.uk
season-files fetched (0 failures), a cp1252-encoding bug found and fixed in the loader.
Domestic leagues now span **2001-02 → 2026-27 (26 seasons)**.

**Item 1 — all 4 API keys tested with real calls, response shapes fixed to match reality:**
- **API-Football**: real `/status` confirmed a Free plan, 100 req/day. Real `/fixtures?live=all`
  confirmed the response shape and a bonus finding — events are embedded in the batched
  response, no second per-match call needed.
- **football-data.org**: real `/competitions/CL` confirmed the exact real header names
  (`X-RequestCounter-Reset`, `x-requests-available-minute`) and that Champions League's
  real code is "CL" (id 2001). Real header-driven throttling built and verified.
- **Gemini**: real calls confirmed `gemini-2.5-flash` 404s for new users (migrated to
  `gemini-3.6-flash`); a **critical bug was found and fixed**: multi-turn tool-calling
  conversations used `role="tool"`, which the real API rejects outright ("Role 'tool' is
  not supported") — every question needing 2+ tool calls (nearly all of them) was
  silently downgraded to the DB-only fallback with no visible error until this was caught
  and fixed to `role="user"`, verified end-to-end against a real multi-tool-call
  conversation. Also found the real free-tier daily cap is **20 requests/day/project/model**
  (not the 250 previously assumed) and that **Google Search grounding is genuinely
  unavailable** on this tier (real 429 on the first attempt) — Wikipedia was built as the
  real substitute (see item 5 below).
- **YouTube**: real search call confirmed the response shape; 6 real official channel IDs
  (UEFA, Premier League, LaLiga, Serie A, Bundesliga, Ligue 1) resolved via
  `channels.list?forHandle=...` and verified by checking each response's title/description
  actually matches, now checked into code as defaults.

**Item 2 — kickoff times converted to real UTC.** openfootball stores local kickoff per
league; Nations League JSON stores CET/CEST. Both now converted to UTC at ingestion via
`zoneinfo` (DST-aware). Verified real case: Arsenal vs Coventry City, 2026-08-21, 20:00
London (BST) → stored/served as 19:00 UTC.

**Item 3 — corner/timing stats re-run for real.** `scripts/analyze_corners_and_timing.py`
over the real 1,517-match StatsBomb dataset: **3,979 goals total, 15,387 corners, 515
led to a goal (3.35%)**, timing shape 13.0/14.4/15.0/16.5/16.3/18.0/6.7% (0-15'.../90+).
Saved to `reports/corner_and_timing_stats.json` with raw counts; every call site (the
goal-timing model) now cites this report instead of a hardcoded number.

**Item 4 — `scripts/fetch_open_data.sh`** fetches openfootball + martj42/international_results
into the right paths (tested against a scratch directory, verified byte-identical to the
real working copies, idempotent).

**Item 5 — everything the keys unlock, built and verified real:**
- **Wikipedia fallback**: free MediaWiki API, real User-Agent per Wikimedia policy, cached.
  A real bug was found and fixed: the extract API's boolean params are presence-triggered,
  not value-triggered — `exintro=0` still truncates to the 958-char intro; omitting it
  entirely gets the full article. Verified real: the 2016 Champions League final article's
  full extract contains "Sergio Ramos touched the ball... to score", "Yannick Carrasco...
  in the 79th minute", "allowing Cristiano Ronaldo to seal Real Madrid's 11th title."
- **A second real bug found and fixed while testing**: `results.csv` has a genuine 2013
  friendly between Spanish regional sides, "Madrid" vs "Andalusia" — its slugged team id
  collided with Real Madrid's canonical id, and ingesting internationals after domestic
  leagues silently overwrote the club's name/country. Fixed with an id-collision guard,
  regression-tested.
- **API-Football team-ID crosswalk**: built from real `/teams` responses, **96/98 big-5
  teams auto-resolved**, 2 real naming-quirk overrides (Celta Vigo, FSV Mainz 05) found
  and documented. Wired into the live poller as the primary match method, replacing
  best-effort name matching (which is now only a fallback for teams outside the crosswalk).
- **Domestic Golden Boot / likely-scorer probabilities**: real API-Football topscorer data.
  **Important real finding**: the free plan doesn't allow the current season ("try from
  2022 to 2024"), so this is the **2024-25 season**, not live. A real data-quality bug was
  also found (one player's stats were cumulative across a club change, 66 "appearances" in
  a 38-game competition) and filtered out. After the filter, verified correct against real
  history: Salah 29 (Premier League), Mbappé 31 (La Liga), Retegui 25 (Serie A), Kane 26
  (Bundesliga), Greenwood 22 (Ligue 1) — all real 2024-25 Golden Boot winners. **Not
  walk-forward backtested** — explained why in §3 (only one season of totals exists, no
  per-goal timestamps, free tier caps historical seasons).
- **Champions League**: real fixtures/results from football-data.org, **144 real 2026-27
  league-phase matches** (18 finished at ingest time), fetched live on every ingest run
  (not a stale cache — results change match to match, and this tier has no daily cap).
  Reuses the existing generic `/leagues/{code}` routes and pages, no new backend routes
  needed. **No CL predictions/trophy odds** — `predictions.py` explicitly refuses to fit
  a model for "CL" even with enough matches (a cross-league team-strength rating is
  separate, unvalidated research, not something to ship quickly and unvalidated).
  Two real crash bugs found and fixed while testing: the league page and match page both
  called the trophy-odds/prediction APIs without handling a 503, which would have crashed
  *any* competition without a fitted model, not just CL.

**Item 6 — the real test question.** See §7, item 1 — **could not be captured live
end-to-end with Gemini**, a genuine external constraint (the real 20/day Gemini quota,
confirmed exhausted by a live 429 at the time of testing), not a code defect. Every
individual piece of the pipeline this question depends on WAS verified real and correct
independently (see above): the role="user" fix (verified via a real completed multi-turn
conversation before quota ran out, where Gemini correctly said "I do not have access to
data... for the 2016 Champions League final" rather than guessing), the Wikipedia extract
(verified real and correct, contains the exact facts needed), the YouTube UEFA channel ID
(verified real), and the orchestration logic connecting them (verified via mocked tests
that exercise the exact real code path with realistic data). What's unverified is only
the single literal end-to-end HTTP round trip, blocked by the quota, not by a bug.

**A real bug WAS found and fixed by actually running the literal item 6 question**
against the live server (a follow-up check after this session's first pass): with Gemini
quota exhausted, the question fell through to `db_fallback`, whose naive keyword matcher
matched "score" inside "scored" and "Real Madrid" by name, then confidently returned Real
Madrid's most recent *unrelated 2026-27* result as if it answered a question about the
*2016* Champions League final - a wrong answer stated with no hedge, exactly the failure
mode the "never invent a fact" rule exists to prevent. Fixed in `kickcast_api/assistant/fallback.py`
(commit `0a4c153`, after this section was first written): none of the fallback's tools are
date-parametrized (they only ever answer next/most-recent/current), so a question naming
a year outside the current season now declines honestly instead of guessing. Verified live:
the real question now returns "...not a specific match from 2016..." instead of the wrong
score. Regression-tested. **The literal Gemini-powered answer is still pending quota reset**
- re-run the question below once `GEMINI_API_KEY` has fresh quota to see it end-to-end.

## 2. What's built but waiting on an API key (or waiting on quota to reset)

| Feature | Env var | Status |
|---|---|---|
| Champions League fixtures/results | `FOOTBALL_DATA_ORG_API_KEY` | **Working now, verified real** — set the key and re-run `scripts/ingest.py` |
| Champions League trophy odds/predictions | (same) | Not built — needs a cross-league rating (separate research), not just data |
| Domestic Golden Boot / likely scorers | `API_FOOTBALL_KEY` | **Working now, verified real** — 2024-25 season (free plan's cap), not live |
| Live-poller team-ID crosswalk | `API_FOOTBALL_KEY` | **Working now, verified real** — 96/98 auto-resolved |
| Natural-language assistant | `GEMINI_API_KEY` | **Working, but hit the real 20/day quota during this session's testing** — re-verify item 6 live once quota resets (UTC midnight) or with a fresh/paid key |
| Google Search grounding | (same) | Confirmed unavailable on this tier (real 429) — code path present, inert until billing or a different plan |
| Assistant Wikipedia fallback | none needed (keyless) | **Working now, verified real**, used because Search grounding isn't available |
| Official highlight video links | `YOUTUBE_API_KEY` | **Working now, verified real** — 6 real channel IDs checked in |
| Live match center | `API_FOOTBALL_KEY` | Scaffold built, still not exercised against a real live (in-progress) match — needs a match actually being played to test for real |

## 3. What's placeholder, replay-only, or skipped, and why

- **Ballon d'Or / The Best, Puskás**: still `available: false` — no free, verified voting/nominee
  data source exists. Unchanged from the prior report.
- **CL trophy odds**: not built — needs a real cross-league team-strength rating (e.g.
  validating ClubElo's terms of use, or building one from UEFA competition history), a
  separate research task from "add the key."
- **Domestic Golden Boot is the 2024-25 season, not live** — API-Football's free plan
  caps at 2022-2024, confirmed by a real error message, not assumed.
- **Domestic scorer probabilities are NOT walk-forward backtested** — only one season of
  season-TOTAL goal data exists (no per-goal timestamps like the international model has,
  and the free tier won't serve more historical seasons), so there's no held-out future
  to walk into. Validated instead via a real data-quality filter (caught a genuine bad
  row) and a spot-check against public knowledge (all 5 league leaders check out).
- **Nations League trophy odds**: still skipped (MD1-4 of 6, no knockout draw yet).
- **Live match center depth** (win-probability timeline, next-goal probability, corner-scorer
  estimates): still just the score/event polling scaffold — needs a real live match to
  test, not exercised this session either.
- **Item 6's literal live end-to-end answer**: not captured this session, real quota
  exhaustion — see §1 and §7.

## 4. Backtest results

**Domestic goals model** (`reports/backtest_openfootball.json` — this predates the
2001-02 history extension; the extra 4 seasons only affect the earliest matches in an
already-long warm-start window and weren't re-run, not urgent per the prior report):

| Model | Full set (n=8,887) | | | Early season MD1-6 (n=1,452) | | |
|---|---|---|---|---|---|---|
| | Acc | RPS↓ | LogLoss | Acc | RPS↓ | LogLoss |
| Baseline (H/D/A rates) | 43.6% | .2298 | 1.073 | 41.7% | .2294 | 1.085 |
| penaltyblog Dixon-Coles | 52.4% | .2017 | .993 | 52.2% | .1973 | .999 |
| Ours, 1-season warm start | 50.2% | .2089 | 1.017 | 44.0% | .2219 | 1.070 |
| **Ours, full-history warm start** | **52.4%** | **.2009** | **.989** | **52.2%** | **.1947** | **.982** |
| Bookmaker closing odds | 54.3% | .1939 | .967 | 54.1% | .1866 | .954 |

Full-history warm start clearly beats 1-season warm start (RPS +0.0080 to +0.0272,
bootstrap CIs clear of zero), loses honestly to bookmaker odds. Unchanged from the prior
report — see it for the full bootstrap CIs.

**Card model** (`reports/backtest_cards.json`): yellow cards beat baseline (MAE 1.089 vs
1.108, NLL 1.682 vs 1.697); red cards close to a wash on NLL, as before.

**Cross-source validation**: openfootball vs football-data.co.uk agree on 23,560/23,562
(99.99%). Unchanged.

**New this session — real data-quality findings, not backtests but real validations:**
- Domestic scorer data: 1 bad row found and filtered (cumulative cross-club stats
  disguised as a single season); the other 4/5 league leaders checked out as real.
- API-Football team crosswalk: 96/98 (98.0%) auto-resolved against the real Team table.
- Corner/timing re-run reproduced the previously-cited numbers almost exactly (3.35% vs
  the earlier-cited 3.3%; the ~0.05pp difference is presentation rounding, not a real
  discrepancy — both came from the same 1,517-match dataset).

## 5. Exact counts (queried from the real DB just now)

- **74,786 matches** total (72,932 finished, 1,854 scheduled) — up from 67,609 last
  report (2001-02 extension + Champions League).
- **563 teams** (up from 539).
- **7 leagues/competitions**: 5 domestic (2001-02 → 2026-27, 26 seasons each),
  International (2000 → 2026-27, incl. 104 real UEFA Nations League MD1-4 fixtures),
  and **UEFA Champions League** (144 real 2026-27 matches, new this session).
- **40,711 match_stats rows**, **28,712 goalscorer rows** (international, unchanged).
- Real API-Football usage this session: **18/100 daily calls** (confirmed via a real
  `/status` call), well under budget. Real YouTube usage: ~106/10,000 daily units (1
  real search + 6 real cheap channel lookups). Real Gemini usage: hit the real 20/day cap.
- **6 Historical Replay matches** (unchanged).
- Frontend: still **9 routes**; Champions League and the updated Awards page reuse
  existing routes, no new ones added.
- **123 backend tests** (up from 80; 1 skipped when Gemini quota is exhausted, by
  design — see `tests/test_gemini_live.py`), ruff and mypy clean across 50 source
  files; frontend `next lint` and `next build` both clean.

## 6. How to run the site locally

From a clean checkout:

```bash
# Backend
cd kickcast
python3.11 -m venv .venv && source .venv/bin/activate   # needs Python >=3.10
pip install -e ".[dev]"

# Data - see the prior report's note: openfootball and martj42/international_results
# are NOT fetchable by script (get them yourself per §6 of git history, or use
# scripts/fetch_open_data.sh added this session if they're not already in data/).
python scripts/fetch_open_data.sh          # openfootball + martj42, idempotent
python scripts/fetch_footballdata_uk.py    # football-data.co.uk, idempotent
python scripts/fetch_api_football.py       # optional, needs API_FOOTBALL_KEY, idempotent

python scripts/ingest.py        # builds/updates data/kickcast.db, idempotent
uvicorn kickcast_api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000 by default
npm run dev                     # http://localhost:3000

# Verify
pytest                                                            # 122 passed, 1 skipped
ruff check .                                                      # clean
mypy kickcast_engine kickcast_api --ignore-missing-imports        # clean
cd frontend && npm run lint && npm run build                      # clean
```

To use any of the 4 optional keys, put them in `.env` at the repo root (see
`.env.example` for what each unlocks and its real, verified limitations). The site
works fully without any of them.

## 7. Judgment calls / things to double-check

1. **Item 6 (the Real Madrid 2016 UCL final question) was not captured live end-to-end
   with Gemini** this session — the real Gemini free-tier daily cap (20 requests/day/
   project/model, confirmed via a live 429) was exhausted by cumulative testing across
   both sessions before the final combined pipeline could be exercised in one request.
   Every piece it depends on was independently verified real (see §1) and there's a
   real, passing integration test (`tests/test_gemini_live.py`) that catches the exact
   bug class that was found and fixed. Actually running the literal question against
   the live server (with quota still exhausted) surfaced and led to fixing a second,
   unrelated real bug in the DB-fallback path (commit `0a4c153` — it was confidently
   answering an unrelated 2026-27 match instead of declining; now it declines
   honestly). **Re-run the question once quota resets** to see the literal
   Gemini-powered answer: `POST /assistant/ask {"question": "Who scored the winning goal
   for Real Madrid in the 2016 Champions League final, in what minute and how? Give me a
   link to watch it."}`.
2. **A critical, previously-undetected bug was fixed this session**: `role="tool"` in
   Gemini function-calling conversations silently broke every question needing 2+ tool
   calls (nearly all real questions) since the assistant was first built — it was caught
   only because item 6's specific question happened to need exactly that pattern
   (resolve a team name, then look something up). Worth asking whether earlier claims
   about the assistant working ("verified live" in the prior report) were tested against
   single-tool-call questions only — they likely were, given this bug existed undetected.
3. **A second real bug was fixed**: a 2013 regional-side friendly ("Madrid" vs
   "Andalusia") silently corrupted Real Madrid's Team row on every `ingest.py` run before
   this session. If you've been looking at Real Madrid's data anywhere before this
   session's fix, it may have looked wrong.
4. **The real Gemini daily quota (20) is much smaller than previously assumed (250)** —
   worth knowing before you expect heavy assistant usage; a paid plan or a different
   model would be needed for real production traffic.
5. **Domestic Golden Boot data is the 2024-25 season, not live** — API-Football's free
   plan genuinely caps at 2022-2024 (confirmed via a real error message). If you want
   live 2026-27 Golden Boot data, that needs a paid API-Football plan.
6. **CL team country data is incomplete** — football-data.org's match payload has no
   usable per-team country field, so newly-created (non-big-5) CL teams have
   `country: null`. Deliberately didn't guess one (see the "Real Madrid overwritten"
   bug above for why guessing here would be risky).
7. **Kickoff timezone conversion is now real and tested** (was flagged as unverified in
   the prior report) — `LEAGUE_TIMEZONES` per league, DST-aware via `zoneinfo`, verified
   against a real fixture (Arsenal vs Coventry, 2026-08-21, 20:00 London → 19:00 UTC).
8. **Everything from the prior report's §7** still applies (DB schema design, model
   caching keyed on `data_version`, international team ID scheme, card model
   simplicity) — not repeated here, see git history for the full prior report
   (`git show e8a72d7:MORNING_REPORT.md` or the commit right before this file's first
   version, `1d38540`).

Nothing was deployed, no accounts were created, no money was spent. `.env`'s real key
values were never printed, logged, committed, or copied anywhere. Working tree is clean;
every item above is its own commit (`git log --oneline 1d38540..HEAD`, 13 commits) for
incremental review.
