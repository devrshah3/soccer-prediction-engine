const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type League = {
  code: string;
  name: string;
  country: string | null;
  kind: "domestic_league" | "international" | "continental_cup";
};

export type TeamRef = { id: string; name: string };

export type Match = {
  id: number;
  league_code: string;
  season: string;
  date: string;
  kickoff: string | null;
  round: string | null;
  status: "scheduled" | "finished";
  home_team: TeamRef;
  away_team: TeamRef;
  home_goals: number | null;
  away_goals: number | null;
  neutral: boolean;
  source: string;
  // Provider live state (API-Football poll) - present only for a not-yet-finished match we
  // have polled data for; see kickcast_api/serialize.py.
  live?: LiveInfo | null;
  // Goals we have for a finished or in-progress match (kickcast_api/match_events.py); absent
  // when no source has any - the UI then shows the score alone.
  goal_events?: GoalEvent[];
};

export type LiveInfo = {
  match_status: string; // API-Football code: "1H" / "HT" / "2H" / "FT" ...
  minute: number | null;
  home_score: number | null;
  away_score: number | null;
};

// team_id is the team CREDITED with the goal (null if the source's team couldn't be resolved).
export type GoalEvent = { team_id: string | null; scorer: string; minute: number | null; own_goal: boolean; penalty: boolean };
export type CardEvent = { team_id: string | null; player: string; minute: number | null; card: "yellow" | "red" };

// GET /matches/{id} only - goal_events is attached for a finished match (empty if we
// genuinely have none on record, e.g. any domestic match - see kickcast_api/routes/
// matches.py), never present at all for a scheduled one.
export type MatchDetail = Match & { card_events?: CardEvent[] };

// GET /matches?date=... only - prediction/long_range/date_may_change are only present
// for a scheduled match (see kickcast_api/routes/matches.py's matches_by_date).
export type MatchOnDate = Match & {
  prediction?: PredictionSummary | null;
  long_range?: boolean;
  date_may_change?: boolean;
};

export type StandingsRow = {
  team_id: string;
  team_name: string;
  played: number;
  w: number;
  d: number;
  l: number;
  gf: number;
  ga: number;
  gd: number;
  pts: number;
  form: ("W" | "D" | "L")[];
  position: number;
};

export type Standings = {
  league_code: string;
  season: string;
  available_seasons: string[];
  table: StandingsRow[];
};

export type TrophyOdds = {
  league_code: string;
  season: string;
  n_sims: number;
  remaining_fixtures: number;
  model_as_of: string | null;
  teams: {
    team_id: string;
    team_name: string;
    title_pct: number;
    top4_pct: number;
    relegation_pct: number;
    expected_position: number;
    expected_points: number;
  }[];
};

export type TeamDetail = {
  id: string;
  name: string;
  country: string | null;
  league_code: string | null;
  season: string | null;
  position: number | null;
  form: ("W" | "D" | "L")[] | null;
  next_match: Match | null;
};

export type Prediction = {
  model_version: string;
  as_of: string; // data cutoff used for recency weighting - NOT when this was computed, see computed_at
  computed_at: string | null; // real wall-clock time the model was last actually fit - use this for "updated X ago"
  home: string;
  away: string;
  neutral: boolean;
  expected_goals: { home: number; away: number };
  expected_margin: number;
  probabilities: { home: number; draw: number; away: number };
  totals: Record<string, number>;
  btts: number;
  likely_scorelines: { score: string; prob: number }[];
  evidence: "A" | "B" | "C";
  train_matches: { home: number; away: number; total: number };
  home_team: TeamRef;
  away_team: TeamRef;
  match_status: "scheduled" | "finished";
  goal_timing: {
    window: string;
    share_of_goals: number;
    expected_goals: number;
    prob_at_least_one_goal: number;
  }[];
  likely_scorers: {
    available: boolean;
    method?: string;
    source?: string;
    reason?: string;
    home: { player: string; goals_in_window: number; prob_scores: number }[];
    away: { player: string; goals_in_window: number; prob_scores: number }[];
  };
  cards: {
    available: boolean;
    reason?: string;
    home?: { expected_yellow: number; expected_red: number; evidence: "A" | "B" | "C" };
    away?: { expected_yellow: number; expected_red: number; evidence: "A" | "B" | "C" };
  };
};

// The subset of Prediction a list view (MatchRow) actually renders. Returned by
// /predictions/summary, which skips the likely-scorers/cards/goal-timing extras that
// /matches/{id}/prediction computes per match - not worth that cost for every row of a list.
export type PredictionSummary = {
  model_version: string;
  as_of: string;
  computed_at: string | null;
  evidence: "A" | "B" | "C";
  probabilities: { home: number; draw: number; away: number };
};

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The backend runs on a free instance that sleeps after 15 minutes idle and needs up to a minute to
// wake. So: a short timeout (never hang a page on a sleeping server), a short-lived Next.js data cache
// (visitors get the last good data while it wakes; a stale entry is kept if revalidation fails), and a
// distinct error the app-level boundary turns into "Waking up the server..." instead of a raw error.
const REQUEST_TIMEOUT_MS = 8000;
const REVALIDATE_SECONDS = 60;
const UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

class BackendUnavailableError extends Error {
  constructor(path: string) {
    super(`backend unavailable: ${path}`);
    this.name = "BackendUnavailableError";
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new BackendUnavailableError(path); // timeout, DNS, connection refused: the server is asleep or down
  }
  if (UNAVAILABLE_STATUSES.has(res.status)) throw new BackendUnavailableError(path);
  if (!res.ok) {
    throw new ApiError(res.status, `${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type GoldenBootLeague =
  | { available: false; reason: string }
  | {
      available: true;
      tag: "Final";
      season: string;
      source: string;
      top_scorers: { player: string; team_id: string; team_name: string; goals: number; appearances: number }[];
    }
  | {
      available: true;
      tag: "Current season";
      season: string;
      source: string;
      method: string;
      scorers: {
        player: string;
        team_id: string;
        team_name: string;
        goals_so_far: number;
        played_matches: number;
        remaining_matches: number;
        projected_final: number;
        projected_range: [number, number];
        top_scorer_chance: number;
      }[];
    };

export type Awards = {
  season: string;
  available_seasons: string[];
  golden_boot: {
    available: boolean;
    by_league: Record<string, GoldenBootLeague>;
    international_top_scorers_also_available?: {
      reason: string;
      international_top_scorers: { player: string; team_id: string; team_name: string; goals: number }[];
      lookback_days: number;
    };
  };
  ballon_dor: { available: boolean; reason: string };
  puskas: { available: boolean; reason: string };
};

export type GoldenBootBacktest = {
  method: string;
  data_note: string;
  n_test_points: number;
  by_cutoff: {
    cutoff_matchday: number;
    tests: number;
    model_avg_mae: number;
    naive_avg_mae: number;
    model_hits: number;
    naive_hits: number;
  }[];
  summary: {
    model_avg_mae_goals: number;
    naive_avg_mae_goals: number;
    model_hit_rate: number;
    naive_hit_rate: number;
    winner: "model" | "naive";
  };
};

export type ReplayEvent = {
  minute: number | null;
  player: string;
  team_id: string;
  team_name: string;
  own_goal: boolean;
  penalty: boolean;
};

export type ReplayMatch = {
  id: number;
  league_code: string;
  league_name: string;
  league_country: string | null;
  round: string | null;
  date: string;
  kickoff: string | null;
  status: string;
  home_team: TeamRef;
  away_team: TeamRef;
  home_goals: number | null;
  away_goals: number | null;
  has_result: boolean;
  events: ReplayEvent[];
  events_status: "complete" | "partial" | "none" | null;
  prediction: { probabilities: { home: number; draw: number; away: number }; as_of: string; computed_at: string | null; model_version: string; evidence: string | null } | null;
  prediction_result: {
    predicted: "home" | "draw" | "away";
    predicted_probability: number;
    actual: "home" | "draw" | "away";
    actual_probability: number;
    correct: boolean;
  } | null;
  recap: { text: string; mode: "template" | "gemini"; label: string };
};

export type ReplayDay = {
  date: string;
  matches: ReplayMatch[];
  no_events_note: string;
  most_recent_day_with_matches: string | null;
  most_recent_day_with_results: string | null;
};

export const api = {
  leagues: () => apiFetch<League[]>("/leagues"),
  standings: (code: string, season?: string) =>
    apiFetch<Standings>(`/leagues/${encodeURIComponent(code)}/standings${season ? `?season=${season}` : ""}`),
  leagueFixtures: (code: string, status: "scheduled" | "finished" | "all" = "scheduled", limit = 20, season?: string) =>
    apiFetch<Match[]>(
      `/leagues/${encodeURIComponent(code)}/fixtures?status=${status}&limit=${limit}${season ? `&season=${encodeURIComponent(season)}` : ""}`
    ),
  // Fixtures for several leagues in one request (see kickcast_api/routes/batch.py) - used by
  // the homepage instead of one /leagues/{code}/fixtures call per league. `days` bounds
  // "scheduled" results to [now, now + days] - the homepage tries 7 first, then widens to
  // 14 if that comes back thin (e.g. during an international break).
  fixturesByLeagues: (codes: string[], status: "scheduled" | "finished" | "all" = "scheduled", limit = 50, days = 7) =>
    codes.length === 0
      ? Promise.resolve({} as Record<string, Match[]>)
      : apiFetch<Record<string, Match[]>>(
          `/fixtures?leagues=${codes.map(encodeURIComponent).join(",")}&status=${status}&limit=${limit}&days=${days}`
        ),
  // The earliest upcoming domestic-league fixture date, regardless of window - used to
  // show "International break: club football resumes <date>" when nothing domestic falls
  // within the homepage's current window.
  nextDomesticFixtureDate: () => apiFetch<{ date: string | null }>("/fixtures/next-domestic-date"),
  team: (id: string) => apiFetch<TeamDetail>(`/teams/${encodeURIComponent(id)}`),
  teamFixtures: (id: string, status: "scheduled" | "finished" | "all" = "all", limit = 100) =>
    apiFetch<Match[]>(`/teams/${encodeURIComponent(id)}/fixtures?status=${status}&limit=${limit}`),
  trophyOdds: (code: string, season?: string) =>
    apiFetch<TrophyOdds | null>(`/leagues/${encodeURIComponent(code)}/trophy-odds${season ? `?season=${season}` : ""}`).catch(
      (e) => {
        if (e instanceof ApiError && e.status === 503) return null;
        throw e;
      }
    ),
  awards: (season?: string) => apiFetch<Awards>(`/awards${season ? `?season=${encodeURIComponent(season)}` : ""}`),
  awardsMethod: () => apiFetch<GoldenBootBacktest>("/awards/method"),
  // Item 6: the viewer's local "yesterday" (tz = minutes east of UTC) - or an earlier day
  // reached only via the "most recent day" link. The server never serves today or later.
  replayDay: (tzOffsetMinutes: number, date?: string) =>
    apiFetch<ReplayDay>(`/replay/day?tz=${tzOffsetMinutes}${date ? `&date=${encodeURIComponent(date)}` : ""}`),
  match: (id: number) => apiFetch<MatchDetail>(`/matches/${id}`),
  // B.8: every match on a given local date, each scheduled one carrying its (precomputed
  // where possible) prediction plus long_range/date_may_change flags.
  matchesByDate: (date: string, league?: string) =>
    apiFetch<MatchOnDate[]>(`/matches?date=${date}${league ? `&league=${encodeURIComponent(league)}` : ""}`),
  // B.5/B.6: the nearest other date with matches - "forward" for automatic rollover,
  // "nearest" for an empty-date page's "go to the nearest date with matches" link.
  nearbyMatchDate: (date: string, direction: "forward" | "nearest" = "forward") =>
    apiFetch<{ date: string | null }>(`/matches/nearby-date?date=${date}&direction=${direction}`),
  prediction: (id: number) => apiFetch<Prediction | null>(`/matches/${id}/prediction`).catch((e) => {
    if (e instanceof ApiError && e.status === 503) return null;
    throw e;
  }),
  // Probabilities for several matches in one request (see kickcast_api/routes/batch.py) -
  // used by the homepage instead of one /matches/{id}/prediction call per candidate match.
  predictionsSummary: (matchIds: number[]) =>
    matchIds.length === 0
      ? Promise.resolve({} as Record<string, PredictionSummary | null>)
      : apiFetch<Record<string, PredictionSummary | null>>(`/predictions/summary?match_ids=${matchIds.join(",")}`),
  // C.9: when the data was last refreshed - the footer's "fixtures updated X ago".
  meta: () => apiFetch<{ ingested_at: string | null; data_version: string | null }>("/meta"),
};

export { ApiError, BackendUnavailableError };
