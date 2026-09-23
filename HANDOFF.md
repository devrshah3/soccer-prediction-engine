# Soccer Prediction Website — Handoff Brief for Claude Code

## What exists already (in this repo, tested, do not throw away)

- `soccer_engine/models/dixon_coles.py` — pre-match model: Dixon-Coles with analytic
  gradient, time-decay weights, xG-blended training targets, L2 shrinkage, match-weight
  (friendly vs competitive), leakage guard (`fit()` raises if any training match is on/after
  the cutoff date).
- `soccer_engine/evaluation.py` — walk-forward backtest (refit weekly on past-only data),
  RPS / log loss / Brier / calibration (ECE), plus `walk_forward_window` for bounded date ranges.
- `soccer_engine/data/openfootball.py` — loader for `data/openfootball_raw/` (CC0, free,
  13-17 seasons per big-5 league incl. live 2026-27 season): standings table builder,
  per-team fixture list, training-set extractor.
- `soccer_engine/data/statsbomb.py` + `scripts/extract_statsbomb_events.py` — StatsBomb
  Open Data loader + event summarizer (xG, goal timeline, reds, corners). Used for the
  original model validation; re-run only if you need fresh event-level detail.
- `soccer_engine/data/international.py` — loader for `data/results.csv` /
  `data/goalscorers.csv` (martj42/international_results, CC0) for national-team matches.
- `data/nations_league_2026_27_md1_4.json` — real UEFA-published fixtures for the
  2026-27 Nations League, Matchdays 1-4 (Sept 24 - Oct 6 2026), hand-transcribed from
  uefa.com. Matchdays 5-6 (Nov 2026) are not yet needed but easy to add the same way.
- `reports/backtest_2015_16.json` — validated result: on 2015/16 PL/La Liga/Serie A/Ligue1
  (1,517 real StatsBomb matches), walk-forward, tuned only on PL: our xG-blended model beat
  penaltyblog's Dixon-Coles out-of-sample (50.7% vs 48.3% accuracy, 0.1997 vs 0.2054 RPS),
  paired bootstrap 95% CI for the RPS improvement was [0.0013, 0.0104] — real, not noise.
- `scripts/backtest_compare.py`, `scripts/backtest_international.py` — the scripts that
  produced the above; re-run these instead of re-deriving from scratch, and re-run again
  after any model change to prove it didn't regress.
- Full test suite (`pytest`), `ruff`, `mypy` all passing. Keep them passing — every new
  model or data function needs a test, especially a leakage-guard test (assert nothing in
  training is dated on/after the prediction cutoff).

## Ground rules (carried over from prior discussion, do not relitigate)

- **Free-tier-first.** No paid API keys assumed anywhere by default. Every external data
  call must have a working free-tier path. Paid upgrades (API-Football Pro $19/mo,
  football-data.org Livescores €12/mo) are optional config, never required to run the site.
- **Never claim something works with real data unless it's been verified.** Don't build a
  UI panel for a data field we don't actually have a source for — leave it out or label it
  "data not available" rather than fake it.
- **Every prediction must be chronologically backtested** the same way the existing models
  were (walk-forward, refit-before-cutoff, out-of-sample). No "trust me" numbers.
- **Live data will be delayed 2-5 minutes** (polling API-Football's free 100-calls/day tier,
  batched across all live matches). This is accepted and fine — do not try to work around it
  with scraping or unofficial feeds. Every live/near-live UI element must show a
  "last updated Xm ago" timestamp so the delay is honest, not hidden.
- **The assistant never invents facts.** It answers from our own database first (scores,
  scorers, minutes, tables), falls back to Wikipedia for match write-ups, and only calls out
  to a live web-search-backed LLM (Gemini free tier) for things not in our database. Cache
  every AI-generated answer so repeat questions don't cost API calls twice.
- **Copyright/attribution:** StatsBomb Open Data, openfootball (CC0), and
  martj42/international_results (CC0) all need credit in an About/Data Sources page.
  UEFA's fixture list was manually transcribed for personal/educational use — do not
  scrape uefa.com programmatically; when Matchdays 5-6 are needed, transcribe them the
  same way or find a free API's coverage of the Nations League.

## Build order (pick up here)

1. **Fixtures + tables + team pages + match predictions** (in progress — the openfootball
   loader above was just built and validated against real 2026-27 data, e.g. confirmed
   Man City top of the table with 15 pts after 5 games as of Sept 2026). Still needed:
   - A backtest across the full multi-season openfootball history (not just StatsBomb
     2015/16) to confirm the model benefits from 13-17 seasons of training data instead of
     one season — this should fix weak early-season predictions.
   - Since openfootball has no xG, this backtest should run `xg_weight=0` (goals-only mode)
     and confirm it still beats a frequency baseline out-of-sample, the same rigor as before.
   - Wire the loader + model into a small API layer (FastAPI or similar) exposing:
     `/leagues`, `/leagues/{id}/standings`, `/teams/{id}`, `/teams/{id}/fixtures`,
     `/matches/{id}/prediction`.
   - Basic frontend: homepage predictions list (3-way probability bar, not single %, with
     "as of" timestamp), league standings page with Stat Leaders, click-through team page
     (schedule + form + position), match page (pre-match prediction, becomes near-live once
     kickoff passes, becomes result + highlights link after).
2. **Goalscorer probabilities + goal-timing windows.** Real distribution already computed
   from 1,503 StatsBomb matches: 13.0% (0-15'), 14.5% (15-30'), 15.0% (30-45'), 16.5%
   (45-60'), 16.3% (60-75'), 18.0% (75-90'), 6.6% added time — use this as the shape prior,
   scaled by each match's total expected goals. Player-level scorer rates need API-Football
   player stats (free tier) or another free source — find and validate one before building.
3. **Card predictions** (new, not yet started) — team-level yellow/red rate model, home/away
   split, same Dixon-Coles-style structure as goals. Needs a free source of match-level card
   counts (openfootball doesn't have this — check football-data.co.uk CSVs, which include
   card counts alongside results/odds for many leagues/seasons).
4. **Team trophy odds** — Monte Carlo season simulation (prototype already validated on
   2015/16 PL: correctly tracked Leicester's title odds rising from 14% to 47% as they kept
   winning). Needs: (a) league title/top4/relegation — straightforward extension of what
   exists; (b) Champions League — harder, needs a cross-league rating (research ClubElo's
   terms of use, or build one from UEFA competition history in the openfootball/StatsBomb
   data); (c) Nations League/tournaments — use the international.py loader + the
   already-fetched real fixture list.
5. **Assistant** — DB-first answer generation, Wikipedia fallback for match narratives,
   official-channel YouTube Data API search for highlight links, Gemini free tier
   (search-grounded) only as last resort + for natural-language writeup. Cache every answer.
6. **Individual awards tab** — Golden Boot (simulate from scorer rates, same method as #2),
   Ballon d'Or (train on historical voting data, label uncertainty honestly given small
   annual sample), Puskás (no probability — just show nominees + official goal links).
7. **Live match center** — near-live score/event polling (2-5 min delay, batched
   API-Football free-tier calls), live win-probability timeline chart with goal/card/sub
   markers, in-play scorer-of-next-goal estimate. Build last since it depends on #1-3 being
   solid first.

## What NOT to do

- Don't fork/copy any of the GitHub "AI football prediction" repos evaluated earlier
  (FootballGPT/football-ai, AmirMotefaker's WC2026 repo, jarvis-footBall, etc.) — all were
  checked and rejected (no tests, tiny, or require a paid OpenAI key). `penaltyblog` (MIT,
  well-tested) is fine to use as a dependency/comparison baseline, not to copy from.
- Don't scrape Google, UEFA.com programmatically, or any site whose terms would forbid it.
- Don't build any UI claiming real-time (<1 min) live scores — that's what the 2-3 minute
  "as of" delay disclosure is for.
