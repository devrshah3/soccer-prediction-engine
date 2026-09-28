# Deploying the Soccer Prediction Engine

Render runs **only the API**; the frontend runs on **Vercel**.

- **`soccer-prediction-api`** (Render, free web service, defined in `render.yaml` - a Render
  "Blueprint") - the FastAPI backend (Python, `uvicorn`). Build step fetches the free
  open data sources, ingests them into a SQLite database, fits the models, computes trophy
  odds and Golden Boot projections, and precomputes match predictions - all of it *before*
  the service starts, so a cold start serves immediately (see `kickcast_api/artifacts.py`
  and `kickcast_api/build.py`). Render's free instance loses filesystem changes on every
  restart, but the built database and artifacts ship as part of the deploy, so this is fine.
- **The Next.js frontend** (`frontend/`, on Vercel - not part of `render.yaml`). Every page
  that reads live data (`/`, `/leagues`, `/leagues/[slug]`, `/matches/[id]`, `/teams/[id]`,
  `/about`, `/awards`, `/awards/method`, `/replay`) is rendered on demand (`export const
  dynamic = "force-dynamic"`, or already opts into dynamic rendering via
  `searchParams`/dynamic route params) - never statically prerendered at build time, since
  the backend is a separate service and isn't guaranteed reachable while the frontend builds.

Neither needs any API key to run: every optional key in `.env.example` unlocks something
extra (Champions League fixtures, the natural-language assistant, video links, the live
match center) and the site is fully functional without them - see `.env.example` for exactly
what each one does and its free-tier limits.

## First deploy

1. Push this repo to GitHub (already done - `origin` is
   `https://github.com/devrshah3/soccer-prediction-engine`).
2. **API on Render:** in the Render dashboard, **New > Blueprint**, point it at this
   repo/branch. Render reads `render.yaml` and creates the one service,
   `soccer-prediction-api`. It will ask for these variables (all `sync: false`, all may be left
   blank - see `.env.example`): `FRONTEND_ORIGIN`, `FOOTBALL_DATA_ORG_API_KEY`,
   `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `API_FOOTBALL_KEY`. `ADMIN_TOKEN` is not asked for:
   Render generates a random value (`generateValue: true`).
3. First build takes several minutes (fetches ~29 MB of open data, ingests, fits models).
   `scripts/build_deploy.py` fails the build loudly (non-zero exit) if any data step fails or
   the finished database has fewer than 1,000 matches - an empty site is worse than a failed
   deploy. Note the service's URL (e.g. `https://soccer-prediction-api.onrender.com`).
4. **Frontend on Vercel:** import the same GitHub repo, set the **Root Directory** to
   `frontend`, and add one environment variable, `NEXT_PUBLIC_API_URL` = the API URL from step 3.
   It is baked into the client bundle at build time, so set it *before* the first build;
   otherwise redeploy after setting it.
5. Set `FRONTEND_ORIGIN` on `soccer-prediction-api` to the Vercel URL (no trailing slash) and
   redeploy it. CORS is closed by default in production - nothing is allowed until this is
   set (see `kickcast_api/settings.py:frontend_origins`). If you add a custom domain or use
   Vercel preview URLs, `FRONTEND_ORIGIN` takes a comma-separated list.

## What changes in production (`APP_ENV=production`)

Set automatically by `render.yaml` (`APP_ENV=production`). See `kickcast_api/settings.py` for the exact defaults;
in short:
- `/docs`, `/redoc`, `/openapi.json` are disabled.
- CORS is limited to `FRONTEND_ORIGIN` (nothing, until that's set - not a wildcard).
- No model fitting, Monte Carlo simulation, or provider call ever happens inside a request
  (`PRECOMPUTED_ONLY=true`) - only at build time, in the nightly job (03:00 UTC), or via the
  lightweight background catch-up that runs on wake-up and every few hours while awake
  (`kickcast_api/catchup.py`) to cover the gap while Render's free instance was asleep.
- API-Football is off by default even if a key is set (`ENABLE_API_FOOTBALL=false`): its
  terms have not been confirmed to permit displaying its data on a public site, so the live
  match center reports "not enabled on this deployment" and Historical Replay is shown
  instead. Set `ENABLE_API_FOOTBALL=true` explicitly if you've checked the terms for your
  own plan and are comfortable with them.
- ESPN's public scoreboard (`kickcast_api/live/espn.py`) is an undocumented endpoint with no
  published terms, used as a keyless source for scores, scorers and cards (it covers the
  Nations League and the scorers/cards of the domestic leagues, which nothing else we have
  does). It is **on** in this deployment (`ENABLE_ESPN=true` in `render.yaml`, a deliberate
  choice - set it to `"false"` to turn it off). The server reads it itself: at every start
  and after every catch-up it re-reads the last 7 days, and during a match window it polls
  every 10 minutes. Nothing ESPN-derived is committed to the repo. Without it, a deployed
  site only has what the open sources knew at build time - typically no results at all for
  the last few days (the martj42 CSV lags by weeks) and no scorers for club matches.

## Seed snapshot (run before pushing)

Render's free disk resets to the build snapshot, so anything the running server learned is
gone after a restart. `seed/seed.json.gz` (committed, well under 1 MB) carries **open-licensed**
result / goal-event / match-stat rows (martj42 CC0, openfootball CC0, football-data.co.uk) for
the current season window; it is loaded at build time (`scripts/build_deploy.py`) and at
startup, before any refresh, and only ever fills gaps - it never overwrites a finished match.
It deliberately contains nothing from ESPN or API-Football.

Before pushing a release, from a machine with an up-to-date local database:

```
python scripts/export_seed.py          # writes seed/seed.json.gz, prints its size (cap: 5 MB)
git add seed/seed.json.gz && git commit -m "Refresh seed snapshot"
```

## Testing the build step locally before deploying

```
pip install -r requirements.txt
python scripts/build_deploy.py
```

This runs the exact steps Render's build does. It's safe to re-run (idempotent upserts) and
does not touch anything outside `data/`. It makes real network calls to the free data
sources (and one football-data.org call for the Champions League if
`FOOTBALL_DATA_ORG_API_KEY` is set) - don't run it in a tight loop.

## Known gaps / not done

- `ADMIN_TOKEN` (generated by Render, currently unused), `RATE_LIMIT_PER_MINUTE`, `ASSISTANT_RATE_LIMIT_PER_MINUTE`/`_HOUR`,
  `TRUSTED_PROXY_HOPS`, `IP_HASH_SALT`, `GEMINI_PER_VISITOR_DAILY`, `MAX_QUESTION_CHARS`
  are all read by `kickcast_api/settings.py` but nothing in the API currently calls them -
  there is no rate-limiting middleware and no admin-authenticated recompute endpoint yet.
  Until that's built, the only real defenses against abuse are the providers' own daily
  quotas (Gemini, YouTube, API-Football, football-data.org) and Render's free-tier limits.
- No database migration framework - `kickcast_api/db.py` has a small additive-only
  substitute (`_MIGRATIONS`) for adding nullable columns to an existing table. A real schema
  change (renaming/dropping a column) needs a manual one-off script.
- Not yet deployed for real - this file and `render.yaml` have not been exercised against an
  actual Render account.
