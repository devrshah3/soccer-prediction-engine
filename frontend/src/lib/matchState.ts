import type { Match } from "./api";

// Last-resort fallback only: used to call a match Finished when NO source has explicitly
// marked it finished (football-data.org / API-Football final status, or openfootball /
// martj42's own finished marker - all surface as Match.status === "finished" or a final
// live.match_status code). 150 min = 90 + stoppage + half-time + a margin for extra time
// that isn't otherwise flagged.
export const FINISHED_FALLBACK_MINUTES = 150;

// API-Football's full-time status codes (same set as kickcast_api/live/results_updater.py).
const FINISHED_PROVIDER_CODES = new Set(["FT", "AET", "PEN"]);

export type MatchScore = { home: number; away: number };

export type MatchState =
  | { kind: "scheduled" }
  | {
      kind: "live";
      minutesSinceKickoff: number;
      // true only when a provider live flag (Match.live) says the match is in play;
      // false means we're inferring "live" from elapsed time since kickoff (fallback).
      providerLive: boolean;
      providerMinute: number | null; // the provider's match clock, when it gave one
      score: MatchScore | null; // null = no live score source; never faked
      updatedAt: string | null; // when the provider data was last polled (ISO), for "updated X min ago"
    }
  | { kind: "finished"; explicit: boolean; score: MatchScore | null };

type StateInput = Pick<Match, "status" | "date" | "kickoff"> & Partial<Pick<Match, "home_goals" | "away_goals" | "live">>;

function scoreOf(home: number | null | undefined, away: number | null | undefined): MatchScore | null {
  return home != null && away != null ? { home, away } : null;
}

// Computed at request time (pages fetch with cache: "no-store"), purely from UTC kickoff
// vs UTC now - no viewer-timezone dependency, so this is safe to compute on the server
// without a hydration mismatch (unlike KickoffTime's local-time display, which needs the
// client).
// `now` is injectable (defaults to the real clock) so tests can exercise "before
// kickoff"/"mid-match"/"long after" without waiting on the real clock.
export function matchState(match: StateInput, now: Date = new Date()): MatchState {
  const live = match.live ?? null;

  // 1. Explicit finished flag from a source.
  if (match.status === "finished") {
    return { kind: "finished", explicit: true, score: scoreOf(match.home_goals, match.away_goals) };
  }
  if (live && FINISHED_PROVIDER_CODES.has(live.match_status)) {
    return {
      kind: "finished",
      explicit: true,
      score: scoreOf(live.home_score ?? match.home_goals, live.away_score ?? match.away_goals),
    };
  }

  if (!match.kickoff) return { kind: "scheduled" }; // no kickoff time on record - can't compute elapsed
  const kickoffMs = new Date(`${match.date}T${match.kickoff}:00Z`).getTime();
  if (Number.isNaN(kickoffMs)) return { kind: "scheduled" };
  const minutesSinceKickoff = (now.getTime() - kickoffMs) / 60000;
  if (minutesSinceKickoff < 0) return { kind: "scheduled" };

  // 2. LAST-RESORT FALLBACK: no source gave an explicit finished flag, so assume the match
  //    is over once kickoff + 150 min has passed.
  if (minutesSinceKickoff >= FINISHED_FALLBACK_MINUTES) {
    return { kind: "finished", explicit: false, score: scoreOf(match.home_goals, match.away_goals) };
  }

  // 3. Live. Score comes from the provider's live state, else from goals the results
  //    updater wrote onto a not-yet-finished match; null when neither exists.
  return {
    kind: "live",
    minutesSinceKickoff,
    providerLive: live != null,
    providerMinute: live?.minute ?? null,
    score: scoreOf(live?.home_score ?? match.home_goals, live?.away_score ?? match.away_goals),
    updatedAt: live?.updated_at ?? null,
  };
}
