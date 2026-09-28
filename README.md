# Soccer Prediction Engine

**Live site:** _URL to be added_

A free soccer prediction site: for every upcoming match in the Premier League, La Liga, Serie A,
Bundesliga, Ligue 1 and international football (World Cup, Nations League and more) it shows
win/draw/loss probabilities, likely scorelines, expected goals, both-teams-to-score and over/under,
each labelled with how much evidence sits behind it. Champions League fixtures and results are
shown too, without predictions (no validated model for that competition yet). Predictions come from a Dixon-Coles model blended with expected
goals and backtested walk-forward with no lookahead (results below); results, scorers and cards
update through the day, and past match days can be replayed. A FastAPI backend serves the model and a
Next.js frontend displays it.

## Run it locally

Needs Python 3.10+ and Node 22.

```bash
# 1. Backend: fetch the free open data, ingest it, fit the models, precompute predictions
pip install -e ".[dev]"
python scripts/build_deploy.py            # several minutes the first time; safe to re-run
cp .env.example .env                      # optional: every key in it unlocks something extra
uvicorn kickcast_api.main:app --port 8000 # http://localhost:8000/health

# 2. Frontend (second terminal)
cd frontend
cp .env.example .env.local                # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                               # http://localhost:3000
```

The site works with no API keys at all. Deploying (API on Render, frontend on Vercel) is in
[DEPLOY.md](DEPLOY.md).

## Results (real data, no peeking)

Tested on the complete 2015/16 Premier League, La Liga, Serie A and Ligue 1 seasons
(1,517 matches, StatsBomb Open Data). Protocol:

- Refit every week using **only matches played before that week**; there's an assertion
  that fails if any future match gets into training.
- Tuned **only on the Premier League**. La Liga, Serie A and Ligue 1 are untouched
  out-of-sample tests.

Out-of-sample average (838 matches):

| Model | Accuracy | RPS (lower = better) | Log loss |
|---|---|---|---|
| Baseline (league home/draw/away rates) | 45.5% | 0.2270 | 1.0723 |
| penaltyblog Dixon-Coles (goals) | 48.3% | 0.2054 | 1.0110 |
| Ours, goals only | 48.9% | 0.2033 | 1.0024 |
| **Ours, xG-blend** | **50.7%** | **0.1997** | **0.9918** |

Paired bootstrap vs penaltyblog on the same 838 matches:
- RPS improvement: 0.0057, 95% CI [0.0013, 0.0104]
- Log-loss improvement: 0.0192, 95% CI [0.0031, 0.0349]

Full per-league tables and calibration are in `reports/backtest_2015_16.json`.

**Caveats**
- These are single seasons with no previous-season warm start, so early-season
  predictions are weak.
- 2015/16 is only one sample of seasons.
- Accuracy will differ on other leagues and years; this is not a promise of future accuracy.

## What makes it better

1. **xG-blended training.** Team strength is fit on 75% expected goals + 25% actual goals.
   Goals are noisy; xG reflects chance quality and reveals true strength faster. The
   Dixon-Coles low-score correction still uses real scorelines.
2. **Shrinkage toward league average**, so teams with few matches don't get extreme ratings.
3. **Evidence tiers** (A/B/C) on every prediction, so the site can flag thin data or unseen teams.
4. **Hard leakage guard**: `fit()` refuses any training match on or after the cutoff date.

## Layout

```
kickcast_api/                           FastAPI backend: routes, precompute, live results jobs
frontend/                               Next.js site
kickcast_engine/models/dixon_coles.py   pre-match model (analytic gradient, xG blend, leakage guard)
kickcast_engine/evaluation.py           walk-forward backtest, RPS / log loss / Brier / calibration
kickcast_engine/data/statsbomb.py       StatsBomb open-data loader with cache
scripts/extract_statsbomb_events.py   streams event files -> per-match xG, goal timeline, reds, corners
scripts/backtest_compare.py           head-to-head backtest (baseline vs penaltyblog vs ours)
tests/                                unit tests incl. leakage checks
```

## Reproduce

```bash
pip install -e ".[dev]"

# Free/keyless data. Both steps are idempotent (skip what's already present, safe to
# re-run) - a genuinely fresh clone needs both before `python scripts/ingest.py` works:
scripts/fetch_open_data.sh          # openfootball + martj42/international_results
python scripts/fetch_footballdata_uk.py   # football-data.co.uk (stats/cards/odds, 2001-02+)

mkdir -p data/sb
for p in "2 27" "11 27" "12 27" "7 27"; do set -- $p
  curl -s -o data/sb/matches_$1_$2.json \
    https://raw.githubusercontent.com/statsbomb/open-data/master/data/matches/$1/$2.json; done
python scripts/extract_statsbomb_events.py data/sb_summaries.jsonl data/sb/matches_*_27.json
python scripts/backtest_compare.py data/sb_summaries.jsonl data/sb reports/backtest_2015_16.json
python scripts/analyze_corners_and_timing.py data/sb_summaries.jsonl reports/corner_and_timing_stats.json
pytest && ruff check . && mypy kickcast_engine --ignore-missing-imports
```

## Keeping data fresh

Fixtures, results, and predictions don't update on their own unless something re-runs the
pipeline. Two things happen automatically once the backend (`uvicorn kickcast_api.main:app`)
is running, no extra setup:
- **Prediction precompute**: every scheduled match in the next 90 days gets a stored
  prediction nightly at 03:00 UTC, and again right after any `scripts/ingest.py` run (see
  `kickcast_api/precompute.py`). This doesn't touch fixtures/results, only predictions.
- **Live results**: a poll every 10 minutes, but only during an actual match window and with a
  short catch-up for missed ones - see `kickcast_api/live/results_updater.py`. Sources are
  API-Football (needs `API_FOOTBALL_KEY`, 100 calls/day) and ESPN's public scoreboard (keyless);
  API-Football is off by default in production; ESPN is on in the Render blueprint - see [DEPLOY.md](DEPLOY.md).

Fixtures and results themselves (openfootball, martj42, football-data.org) need a real
re-ingest, which needs network access this project doesn't run for you automatically.
One command does the whole thing - re-fetch, re-ingest (idempotent), recompute
predictions, and log what changed (new fixtures, moved dates, new results):

```bash
python scripts/daily_refresh.py
```

To run it daily without touching anything, add a real crontab entry (adjust the paths):

```
0 6 * * * cd /path/to/kickcast && .venv/bin/python scripts/daily_refresh.py >> logs/daily_refresh.log 2>&1
```

football-data.org (Champions League) is refreshed as part of the same `ingest.py` run
this script calls - its client already enforces the real 10 calls/minute limit
(`kickcast_api/football_data_org.py`), so no separate schedule is needed for it.

When a fixture's date or time changes between two ingests, it's matched by competition/
season/round/teams and updated in place (not duplicated) - the previous date/kickoff is
kept on the row (`Match.previous_date`/`previous_kickoff`) rather than silently discarded.
This needs a real `round` value to work (true for domestic "Matchday N" rounds and
Nations League groups); a competition without one falls back to being treated as a new
fixture instead of a moved one.

The homepage footer shows "fixtures updated X ago" from `GET /meta`'s `ingested_at`, so
staleness is always visible, never hidden.

## Data credit

Historical data: [StatsBomb Open Data](https://github.com/statsbomb/open-data),
[openfootball/football.json](https://github.com/openfootball/football.json) (CC0 - fetched via
`scripts/fetch_open_data.sh`, which pulls a tarball of the repo into `data/openfootball_raw/`),
[martj42/international_results](https://github.com/martj42/international_results) (CC0 - same
script, `results.csv`/`goalscorers.csv` into `data/`).
Comparison model: [penaltyblog](https://github.com/martineastwood/penaltyblog) (MIT).

Fixtures and results for the Champions League: [football-data.org](https://www.football-data.org/)
(free tier, needs `FOOTBALL_DATA_ORG_API_KEY`; fetched by `scripts/ingest.py` within its 10
calls/minute limit and used as a source for scores in the leagues it covers).

Live scores, scorers and cards, both optional: [API-Football](https://www.api-football.com/) (free
plan, key required) and ESPN's public scoreboard (undocumented, keyless, no published terms).
API-Football is off in a production deploy unless you turn it on; ESPN is on in the Render blueprint (see DEPLOY.md).

Match stats, cards and historical closing odds: [football-data.co.uk](https://www.football-data.co.uk/).
No formal license/terms-of-use text restricting research or personal use was found on the site
(checked the homepage, `/notes.txt` and `/disclaimer.php`); it's a long-established free dataset
widely used in football-analytics research, with no robots.txt restriction either. Downloaded
once into `data/footballdata_uk/` via `scripts/fetch_footballdata_uk.py` (not scraped live per
request), with a manifest recording what was fetched and when.

Match write-ups and other facts not in our own database (the "Ask about soccer" assistant's
outside-DB source): [Wikipedia](https://en.wikipedia.org/), content licensed
[CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/), fetched live per question via the
free MediaWiki Action API with a descriptive User-Agent (see `kickcast_api/assistant/wikipedia.py`)
and cached so a repeated question never re-fetches. Every assistant answer sourced from Wikipedia
cites the specific article and URL used.
