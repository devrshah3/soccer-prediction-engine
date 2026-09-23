const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type League = {
  code: string;
  name: string;
  country: string | null;
  kind: "domestic_league" | "international";
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
    reason?: string;
    home: { player: string; goals_in_window: number; prob_scores: number }[];
    away: { player: string; goals_in_window: number; prob_scores: number }[];
  };
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

export const api = {
  leagues: () => apiFetch<League[]>("/leagues"),
  standings: (code: string, season?: string) =>
    apiFetch<Standings>(`/leagues/${encodeURIComponent(code)}/standings${season ? `?season=${season}` : ""}`),
  leagueFixtures: (code: string, status: "scheduled" | "finished" | "all" = "scheduled", limit = 20) =>
    apiFetch<Match[]>(`/leagues/${encodeURIComponent(code)}/fixtures?status=${status}&limit=${limit}`),
  team: (id: string) => apiFetch<TeamDetail>(`/teams/${encodeURIComponent(id)}`),
  teamFixtures: (id: string, status: "scheduled" | "finished" | "all" = "all", limit = 100) =>
    apiFetch<Match[]>(`/teams/${encodeURIComponent(id)}/fixtures?status=${status}&limit=${limit}`),
  match: (id: number) => apiFetch<Match>(`/matches/${id}`),
  prediction: (id: number) => apiFetch<Prediction | null>(`/matches/${id}/prediction`).catch((e) => {
    if (e instanceof ApiError && e.status === 503) return null;
    throw e;
  }),
};

export { ApiError };
