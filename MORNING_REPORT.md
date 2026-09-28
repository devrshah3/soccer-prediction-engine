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

---

## Session 3 — 2026-09-27: frontend redesign, three real backend bugs found and fixed
with real data, hybrid assistant answers

12 commits this session, `f4518d4`..`783e830` (`git log --oneline d71dfb7..HEAD`). Frontend
work and backend work are separate commits throughout, as requested. Every fix below was
verified against the real running server/real database, not just read from the code -
exact commands and real output are in each commit message.

### Frontend: dark/blue redesign + persistent assistant widget (4 commits)

Full visual redesign (`f4518d4`, `b2b03e2`, `76da8c2`): navy/slate background, blue accent
(was flat black/emerald), team crests (initials avatars - no crest-image pipeline exists),
a real 3-way probability bar everywhere, standings with right-aligned tabular numbers,
tabbed team pages, card-based awards. Verified responsive at 375px; two spots (the match
page hero, team page's next-match line) needed explicit wrapping fixes for long team names.

The `/assistant` full page (`4e83b67`) is gone - the assistant is now a floating chat
bubble on every page, opening into a docked side panel (Intercom-style) with an expand
button that promotes the same conversation to full-screen (ChatGPT-style) without losing
history. Source data renders as inline cards (`AssistantSourceCard`) instead of plain text.

### Real bug #1: homepage connection-pool exhaustion (`fbbcfe2`)

The homepage was firing ~28 concurrent per-request DB sessions on every load (one GET per
league's fixtures, one per candidate match's prediction) against the default SQLAlchemy
pool (size 5, overflow 10 = 15) - a real, reproducible 500 (`sqlalchemy.exc.TimeoutError`)
under ordinary browsing, not just heavy load. Fixed with two new batch endpoints
(`kickcast_api/routes/batch.py`: `GET /fixtures?leagues=...`, `GET /predictions/summary?
match_ids=...`) that do the same work in 3 total requests instead of 28, plus
`pool_size=20, max_overflow=20, pool_pre_ping=True` as a backstop. Verified: 30 sequential
loads across 5 pages and a 15-way concurrent burst of the homepage, zero pool timeouts.

### Real bug #2: homepage showed stale/future fixtures as "upcoming" (`c8554f5`, folded
into further fixes below)

Reported as previously fixed but never actually was (`git log` had no such commit). Real
DB query found La Liga/Serie A's earliest "scheduled" rows were Matchday 38 of 2024-25
(over a year stale, football-data.co.uk/openfootball never marked them finished) and
Ligue 1 had rows from **March 2020** (COVID-era, still "scheduled" 6 years later). Fixed
with a hard `[now, now+7d]` window on the homepage's batch fixtures query.

### A1-A4: the stale-data bug's real root cause, plus a second unrelated data-integrity bug

- **A1** (`f07b753`): the team page's "Next match" hero used a *separate* query from the
  "Upcoming" list below it - real example, the Inter team page: hero showed "Como vs Inter,
  2025-05-23" while (before A2) the list showed the same stale thing, proving they'd
  drifted before. Refactored to one shared query so they structurally cannot diverge again.
- **A2** (`3ab46fa`): found the actual root cause - a source reporting "no score yet" for a
  match whose date has already passed. Patched `scripts/ingest.py`'s `upsert_match` (the
  single write path for every source) to relabel these `not_played` at ingest time, and
  ran a one-time cleanup script against the real DB: **148 stale rows fixed** (`es.1`
  2024-25: 10, `fr.1` 2019-20: 101, `fr.1` 2025-26: 1, `international` 2026-27: 26, `it.1`
  2024-25: 10). Verified: the Inter page now correctly shows "2026-10-10 Inter vs Parma".
- **A3** (`c15f525`): compared `/leagues/es.1/standings` against the real La Liga 2026-27
  table (the brief's reference numbers). Barcelona matched exactly; the rest didn't,
  because **Atlético Madrid's match history was split across two team ids** ("atletico"
  from openfootball's `de Madrid`-suffix mis-canonicalization, "atletico madrid" from
  football-data.co.uk) - two separate standings rows with identical stats. Fixed the
  canonicalization (`kickcast_engine/data/team_aliases.py`) and merged the existing split
  data (`scripts/merge_atletico_madrid_ids.py`): 213 duplicate rows deleted (the same real
  match, ingested twice under two id spellings), 61 renamed onto the correct id. All 5
  standings positions now match the brief's real reference numbers exactly. Added a
  dedicated sort-order test (points, then GD, then GF).
- **A4** (`9d50721`): homepage now widens its window from 7 to 14 days when the 7-day
  result is thin (real example: today, mid-international-break, 7 days = 6 matches, all
  Nations League; 14 days = 20, a real mix once domestic leagues resume Oct 9-10), and
  shows "International break: club football resumes `<date>`" via a new
  `GET /fixtures/next-domestic-date` endpoint when even the widened window has nothing
  domestic in it.

### Assistant: Gemini overuse fixed, then partly un-fixed on purpose (`02e84d5`, `783e830`)

First pass (`02e84d5`): audited real usage and found *every* question was costing a Gemini
call (confirmed - "When does Arsenal play next?" was already cached with `mode: "gemini"`
from earlier testing) on a 20/day quota. Added markdown stripping, a DB-lookup classifier
that skipped Gemini entirely for simple questions, and fixed the DB→Wikipedia→Gemini
ordering (Wikipedia was being tried *after* a wasted tool-calling attempt, not before) -
while fixing that, found and fixed a real Wikipedia search-ranking bug (the raw question
"How did Real Madrid win the 2016 Champions League final?" ranked the 2017 final above the
2016 one; stripping interrogative stopwords before searching fixes it, verified against
the live MediaWiki API).

Second pass, this session's Part B (`783e830`): the brief asked to reverse the "skip
Gemini for lookups" decision - use Gemini for lookups too, but *only* to phrase facts we
already looked up (never to invent new ones), cached by `hash(question + facts)` so a
repeat question costs nothing, with a graceful plain-template-plus-"AI phrasing paused"
fallback when quota runs out or the call fails, and a new `ASSISTANT_GEMINI_FOR_LOOKUPS`
flag to turn the whole thing off if quota gets tight. Modes: `db`, `gemini+db`,
`wikipedia+gemini`, `fallback`.

**Tested for real against the running server with the real key** - the real free-tier
daily quota (20/day) turned out to already be exhausted from this session's own earlier
verification calls (confirmed against the raw Gemini API directly: a real 429
`RESOURCE_EXHAUSTED`, not just our own drifted local counter, which still showed 20/20
remaining because failed calls never increment it). Real result for "When does Arsenal
play next?": `{"text": "Arsenal vs Leeds on 2026-10-10 (Matchday 6). (AI phrasing paused
for today.)", "mode": "db", "cached": false}` on both calls (correctly never caches a
paused/failed answer). The Wikipedia path was also tested for real under the same
exhaustion and correctly fell back to the raw extract + link + paused note.

**Still needs testing once the real quota resets**: the actual success path for both
`gemini+db` and `wikipedia+gemini` against a real call (does the phrasing read naturally,
does the opponent-form/prediction extra actually show up), and a real cache hit following
a real successful compose. The logic for both is verified deterministically via mocks
(`tests/test_assistant.py`), just not yet against a live model response.

Checks at the end of this session: `pytest` 142 passed / 1 skipped (the live-quota test,
skipping correctly on the real exhaustion above - not a regression), `ruff` and `mypy`
clean, frontend `lint` and `build` clean. Nothing was deployed, no money was spent, no
`.env` values were printed or committed.

---

## Session 4 — 2026-09-28: date/schedule rewrite (13 items), 3 more real bugs found

12 commits, `ad83278`..`5101669` (`git log --oneline ad83278^..HEAD`). Every fix below was
verified against the real running server/real database after restarting it, not just read
from the code. Real wall-clock time crossed into 2026-09-28 UTC partway through this
session (a long session) - noted wherever it affects how a specific verification reads
"today".

### A1: the actual root cause of the missing-matches bug

Queried the DB directly first: all 8 real Nations League matches for 2026-09-27 WERE
already in the DB, including Serbia-Netherlands and Norway-Portugal - so the bug was never
ingest/team-mapping. Root cause: the fixtures query sorted only on `date`, never
`kickoff` - ties on the same date fell back to whatever index SQLite used to satisfy the
filter (in practice, alphabetically by home team via the natural-key unique index).
Combined with a default limit of 6 (sized for a domestic matchday, not a Nations League
matchday's 26 simultaneous fixtures), this silently dropped whichever teams sorted late
alphabetically. Fixed: sort by `(date, kickoff)`, raised the default limit to 50 - the
date window is the real bound now. Verified file-count vs DB-count vs endpoint-count
matched for all 13 days from 2026-09-24 to 2026-10-06.

### A2-A4: real match states, a real live-results gap, real prediction-freshness bug

- **A2**: cards/match page now show a real computed state (`matchState.ts`) instead of
  just scheduled/finished - finished shows the score with no probability bar; kickoff
  passed with no score shows "In progress" (<135 min) then "Full time, score pending"
  (beyond it). Match page shows real scorers/minutes when we have them (international
  matches only - `Goalscorer.match_id` isn't populated for domestic) plus a small
  "Pre-match prediction" line.
- **A3**: re-ran `fetch_open_data.sh --force` - martj42's `results.csv` is genuinely stale
  upstream (newest date unchanged, 2026-08-26, before AND after). Made one real
  API-Football call to confirm `/fixtures?date=` (unlike `/teams?season=`) is NOT
  season-restricted on the free tier - 871 real fixtures worldwide, HTTP 200. Built a real
  scheduled results updater (`kickcast_api/live/results_updater.py`, 10-min interval, only
  calls the API inside an actual match window) that updates the canonical `Match` row
  directly - a real gap in the existing live poller, which only ever wrote to a separate
  table and never touched `Match.status`. Real, honest limitation found: the API-Football
  team-id crosswalk only covers the big-5 domestic leagues (98 real ids) - no national
  teams, so this doesn't help Nations League matches yet.
- **A4**: "updated 32d ago" was `as_of` (a data cutoff date), not a computation timestamp -
  a freshly-refit model still showed it because the cutoff itself doesn't move when no new
  results arrive. Added a real `computed_at` (wall-clock, tracked per model-cache entry),
  verified live: `as_of` still 2026-08-27, `computed_at` 0.015 seconds old at request time.

### B.5-B.8: date-aware homepage rewrite

Built in dependency order (B.8 first, since 5-7 all need it): `PrecomputedPrediction`
table + `precompute_predictions()` (every scheduled match in the next 90 days, after every
ingest and nightly at 03:00 UTC) + `GET /matches?date=YYYY-MM-DD` serving from it (falls
back to a live compute for a fixture added after the last precompute run). Real run after
ingest: "572 prediction(s) stored". `isTodaySettled()` (B.5) decides, from an injectable
clock, whether to roll over to the next matchday - unit tested for all 4 specified clock
scenarios. `DatePicker`/`DateMatchList` (B.6) - prev/next arrows, a native date input as
the calendar popover, quick chips, ±90 day range, empty-date recovery via
`GET /matches/nearby-date`. Homepage reorganized (B.7) into Today / Next 7 days / Recent
results. Honest limitation: date grouping is by the backend's stored UTC date; true
per-viewer local-date re-bucketing across a UTC day boundary isn't wired into the live
page (the conversion utility, `localDate.ts`, is real and tested, just not yet consumed by
the page itself - would need a per-viewer timezone signal this server-rendered page
doesn't have without a client round trip).

Set up vitest (the frontend had no test runner at all) - needed for B.5's rollover test
and D.11's component test. Required bumping `@types/node` from a stale `^20` pin to `^22`
to match the Node version actually running here.

### C.9-C.10: scheduled refresh, moved-fixture history, real Nations League MD5-6

- **C.9**: `scripts/daily_refresh.py` is the one command - re-fetch, re-ingest, recompute
  predictions, log what changed (new/moved/newly-finished, by snapshotting the DB before
  and after). Documented with a real crontab line in README.md. Added
  `Match.previous_date`/`previous_kickoff` + a `(league, season, round, teams)` fallback
  match in `upsert_match` so a fixture whose date/time moves updates in place instead of
  duplicating - needs a real `round` value to work, a documented limitation for
  competitions without one. Real migration needed and applied: `create_all()` doesn't
  alter an existing table, so `data/kickcast.db`'s real `matches` table needed an explicit
  `ALTER TABLE` for the two new columns - added a small idempotent migration step to
  `init_db()`, confirmed via `PRAGMA table_info` before/after.
- **C.10**: checked football-data.org (13 competitions, no Nations League) and
  API-Football (`UEFA Nations League Cup` exists, but `season=2026` hits the same
  free-tier block as domestic leagues) for real, both real calls. One real web search +
  one real WebFetch of UEFA.com's own fixtures page, transcribed 52 real MD5-6 fixtures
  into `data/nations_league_2026_27_md5_6.json` (not committed - matches its sibling
  MD1-4 file's existing convention; `data/` is gitignored except one explicit exception).
  Cross-checked every team name against `results.csv`/MD1-4 first: "Czechia" and
  "Türkiye" both already have real `ALIASES` entries. Verified: international row count
  went 25589 -> 25641 (+52 exactly), a real MD5 fixture (Armenia vs Cyprus) has a real
  precomputed prediction.

### D.11 & E.12-13: card decluttering, coverage report, closing the test gaps

Cards no longer show "updated Xd ago · evidence A · dixon-coles-v1" - that's now behind a
new (i) popover (`PredictionInfoPopover`), with a "Prediction may be outdated" tag only
when actually justified (near-term match, prediction >48h stale). `scripts/
coverage_report.py` prints a real 90-day per-league table (30 of the next 91 days have
zero matches across every league, visible not hidden) plus the specific numbers the brief
asked to confirm (Nations League 25666 rows/122 scheduled, CL's real football-data.org
range 2026-09-08..2027-01-27, all 5 domestic leagues' 2026-27 season range). Audited the
5 specific tests the brief asked for: 4 were already covered by earlier commits in this
session; added the one missing one (precompute produces exactly one row per scheduled
match across a set of several, not just one).

### Final proof: the actual homepage output for 2026-09-27

Real wall-clock time had moved to 2026-09-28 by the end of this session, so all 8 of
2026-09-27's matches have now genuinely kicked off and finished (or gone unreported) in
real time - `GET /matches?date=2026-09-27` correctly shows every one of them as
`status: "not_played"` (A2's ingest-time rule: date passed, no score arrived) rather than
inventing a result, and the frontend correctly renders all 8 as "Full time, score
pending", not as upcoming predictions. This is the honest, correct state given real time
has passed and this project has no live-score source that covers Nations League matches
(A3's crosswalk gap) - not a bug. Real output, `GET /matches?date=2026-09-27`:

```
13:00 UTC  Lithuania            vs Azerbaijan             (not_played)
16:00 UTC  Serbia               vs Netherlands            (not_played)
16:00 UTC  Denmark              vs Wales                  (not_played)
16:00 UTC  Austria              vs Kosovo                 (not_played)
16:00 UTC  Gibraltar            vs Andorra                (not_played)
18:45 UTC  Germany              vs Greece                 (not_played)
18:45 UTC  Norway               vs Portugal               (not_played)
18:45 UTC  Israel               vs Republic of Ireland    (not_played)
```

All 8 real matches, including Norway-Portugal and Serbia-Netherlands (the two the original
bug dropped), in correct kickoff order, each in the correct real state.

### What's blocked / needs testing later

- **International live scores**: the new results updater can't help Nations League
  matches until the API-Football team-id crosswalk is extended to national teams (a
  real, separate task - needs its own real `/teams` calls per confederation, same
  treatment as the existing big-5 crosswalk).
- **True per-viewer local-date grouping** across the UTC day boundary: the conversion
  utility exists and is tested, but the live page still groups by the backend's UTC date.
- **Gemini quota** (carried over from Session 3): still real-exhausted as of this session;
  the `gemini+db`/`wikipedia+gemini` success+cache-hit paths are only verified via mocks,
  not a live call yet.
- **Real crontab**: `scripts/daily_refresh.py` is documented with a crontab line in
  README.md but was not actually installed into this machine's crontab (that would be a
  standing change to the user's system - not made without being asked).

Checks at the end of this session: `pytest` 174 passed / 1 skipped, `ruff` and `mypy`
clean, frontend `lint`, `test` (vitest, 22 passed), and `build` all clean. Nothing was
deployed, no money was spent, no `.env` values were printed or committed.

---

## Session 5 — 2026-09-28: dark-blue liquid-glass redesign + leagues/awards/replay rework (items 1-7)

All seven items are committed separately (`git log --oneline` at the bottom). Everything
below was checked against the running stack or the real APIs, not assumed.

### What shipped
1. **Design system + scene** - CSS tokens, `.glass` (blurred containers) vs `.glass-row` (flat rows in
   long lists), fixed non-interactive scene (ball, pitch lines, orbs; motion off under
   `prefers-reduced-motion`), real per-country SVG flags (England = St George's Cross), no logos or
   emoji anywhere, initials circles instead of crests.
2. **Navigation** - floating 4-item Dock (Matches / Leagues / Awards / Replay); top bar is logo + search.
3. **Leagues** - hub of real competitions with "Next: <date> · n matches" from the DB; clean URLs
   (`/leagues/premier-league`), old code URLs 308-redirect; date-driven league view; season selector;
   "Points table" glass sheet (also `?view=table`; "Title odds" tab when available; the button is absent
   when no table can be computed). Found + fixed a real backend gap: `/leagues/{code}/fixtures` ignored
   `season`, so a past season silently showed the current one.
4. **Names, not codes** - central map; fixed the team page, the assistant source card and, found *live*,
   the Gemini assistant answering "...in en.1" (tool results are now scrubbed of `league_code` before the
   model sees them; the DB-only fallback had the same bug). Regression tests on both sides.
5. **Awards** - season selector; current season = live football-data.org leaderboard + projection;
   the one past season with real data (2024-25, domestic) = "Final"; anything else = "No scorer data for
   <season> from our free sources."; (i) popover for source/method; Ballon d'Or / The Best / Puskas
   remain "not available" with reasons. Method page shows aggregate backtest results only.
6. **Replay = yesterday** - viewer-local yesterday only, all competitions; StatsBomb list/routes/data
   file/builder script removed; `/replay/<id>` redirects; credits live on `/about` only.
7. **Polish/QA** - Playwright screenshots (20 JPEGs, 1.8 MB) in `reports/screenshots/`, real bugs fixed.

### Exact data each source returned
**football-data.org `/competitions/{code}/scorers` (one real call each, 2026-09-28):** all 200, real 2026-27
in-progress data. PL: Haaland 5 (5 played) - PD: Raphinha 12 (7), Camello 7, Mbappe 7 - SA: Malen 6 (5) -
BL1: Olise 4, Ebnoutalib 4, Schick 4 - FL1: Gouiri 4, Doumbia 4, Ferran Torres 4 - CL: Demirovic 3,
Ferran Torres 3, Haaland 2. **Past seasons: `?season=2015` -> HTTP 403 "restricted... check your
subscription"** - this plan has no historical scorers at all.
**Awards by season (what the site returns):** 2026-27 -> live projection for all 5 leagues + CL;
2024-25 -> API-Football "Final" tallies for the 5 domestic leagues (Salah 29, Mbappe 31, ...), **CL
unavailable**; every other season, e.g. 2015-16 -> "No scorer data for 2015-16 from our free sources."
**Replay event sources (one real call/read each):**
- martj42 `results.csv`/`goalscorers.csv` (freshly re-downloaded): results end **2026-08-26**, goalscorers
  **2026-07-19** - nothing for the 2026-09-26/27 Nations League days, so yesterday's 8 matches show no
  result yet. Goals-only for internationals when it has caught up; no cards/subs.
- API-Football `/fixtures?date=2026-09-27`: HTTP 200 but `errors.requests: "You have reached the request
  limit for the day"` - **blocked by the daily budget, so current-season access could not be re-tested
  today** (a 2026-09-23 real call already showed the free plan has no current-season access).
- football-data.org `/v4/matches/560583` (Fulham 1-1 Man United): full/half-time score + referee, **no
  goals/bookings/substitutions arrays** - no club-match event timeline exists on our free sources.

### Golden Boot projection - honest numbers
Backtest (internal, real 2015/16 data from 4 full leagues, matchday 5/10/20, 12 test points):
model MAE **7.82** vs naive current-pace **7.81** goals (a tie; naive wins by 0.01); hit rate 33% vs 33%.
By cutoff: MD5 11.48 vs 11.62, MD10 7.90 vs 7.77, MD20 4.08 vs 4.05. **Correction:** the item-5 commit
message says both methods hit the real top scorer at matchday 20 "in all 4 leagues" - wrong; it was 3 of 4
(the Premier League missed: Kane finished ahead of Vardy). Known limitation: a hot start still projects very
high (Raphinha 12 in 7 -> ~52) because observed data dominates the shrinkage once players have played more
than the 5 pseudo-matches of prior; the wide range and title-chance number show the uncertainty, and the
Method page says the method does not clearly beat naive.

### Blocked / not done / caveats
- **API-Football daily quota exhausted**, **Gemini free quota (20/day) used up** by live testing (one live
  test skips because of it; recaps fall back to the labelled template when quota is at the reserve).
- **No pre-match predictions are stored for past dates** in this DB (624 rows, all dated 2026-09-28 or
  later; nothing deletes them), so today's real "yesterday" shows "No pre-match prediction on record".
  The chip is unit-tested; tomorrow's Replay will show it for real for the 2026-09-28 matches.
- Nations League is not a separate competition in our data (it is part of "International"), so there is no
  separate Nations League tile.
- mypy: 5 pre-existing missing-stub errors (scipy, apscheduler), none in new code.
- Dev-only "1 Issue" badge: root cause was opening the dev server on 127.0.0.1 (HMR WebSocket blocked);
  fixed with `allowedDevOrigins`.

### Bugs found by actually looking (Playwright + screenshots)
`/leagues/international` redirect loop (broken since item 3); Dock and assistant bubble not floating
(`.glass` overrode `fixed`); backdrop blur never applied (compiler kept only the `-webkit-` property);
375px card/awards overflow; white page below the fold. All fixed and covered by checks/tests.

### Checks at the end
pytest 196 passed / 1 skipped; ruff clean; mypy only the 5 stub errors; frontend lint + build clean;
vitest 47/47. Both dev servers restarted (API :8000, frontend :3000).
Re-run the screenshots: `cd frontend && node scripts/screenshots.mjs`.
