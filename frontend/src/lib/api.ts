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
  as_of: string;
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

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new ApiError(res.status, `${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type DomesticGoldenBootLeague =
  | { available: false; reason: string }
  | {
      available: true;
      season: string;
      source: string;
      note: string;
      top_scorers: { player: string; team_id: string; team_name: string; goals: number; appearances: number }[];
    };

export type Awards = {
  golden_boot: {
    available: boolean;
    by_league: Record<string, DomesticGoldenBootLeague>;
    international_top_scorers_also_available: {
      reason: string;
      international_top_scorers: { player: string; team_id: string; team_name: string; goals: number }[];
      lookback_days: number;
    };
  };
  ballon_dor: { available: boolean; reason: string };
  puskas: { available: boolean; reason: string };
};

export type ReplayMatchSummary = {
  id: string;
  competition: string;
  season: string;
  date: string;
  home: string;
  away: string;
  home_goals: number;
  away_goals: number;
};

export type ReplayMatch = ReplayMatchSummary & {
  timeline: { type: string; minute: number; team: string | null; player?: string | null; detail?: string | null; player_off?: string | null; player_on?: string | null; card?: string }[];
};

export const api = {
  leagues: () => apiFetch<League[]>("/leagues"),
  standings: (code: string, season?: string) =>
    apiFetch<Standings>(`/leagues/${encodeURIComponent(code)}/standings${season ? `?season=${season}` : ""}`),
  leagueFixtures: (code: string, status: "scheduled" | "finished" | "all" = "scheduled", limit = 20) =>
    apiFetch<Match[]>(`/leagues/${encodeURIComponent(code)}/fixtures?status=${status}&limit=${limit}`),
  // Fixtures for several leagues in one request (see kickcast_api/routes/batch.py) - used by
  // the homepage instead of one /leagues/{code}/fixtures call per league. `days` bounds
  // "scheduled" results to [now, now + days] - the homepage tries 7 first, then widens to
  // 14 if that comes back thin (e.g. during an international break).
  fixturesByLeagues: (codes: string[], status: "scheduled" | "finished" | "all" = "scheduled", limit = 6, days = 7) =>
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
  awards: () => apiFetch<Awards>("/awards"),
  replayMatches: () => apiFetch<{ source: string; matches: ReplayMatchSummary[] }>("/replay/matches"),
  replayMatch: (id: string) => apiFetch<ReplayMatch>(`/replay/matches/${encodeURIComponent(id)}`),
  match: (id: number) => apiFetch<Match>(`/matches/${id}`),
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
};

export { ApiError };
