import type { Match } from "./api";

const IN_PROGRESS_WINDOW_MINUTES = 135;

export type MatchState =
  | { kind: "upcoming" }
  | { kind: "in_progress"; minutesSinceKickoff: number }
  | { kind: "pending_result" }
  | { kind: "finished" };

// Computed at request time (pages fetch with cache: "no-store"), purely from UTC kickoff
// vs UTC now - no viewer-timezone dependency, so this is safe to compute on the server
// without a hydration mismatch (unlike KickoffTime's local-time display, which needs the
// client).
export function matchState(match: Pick<Match, "status" | "date" | "kickoff">): MatchState {
  if (match.status === "finished") return { kind: "finished" };
  if (!match.kickoff) return { kind: "upcoming" }; // no kickoff time on record - can't compute elapsed
  const kickoffMs = new Date(`${match.date}T${match.kickoff}:00Z`).getTime();
  if (Number.isNaN(kickoffMs)) return { kind: "upcoming" };
  const minutesSinceKickoff = (Date.now() - kickoffMs) / 60000;
  if (minutesSinceKickoff < 0) return { kind: "upcoming" };
  if (minutesSinceKickoff < IN_PROGRESS_WINDOW_MINUTES) return { kind: "in_progress", minutesSinceKickoff };
  return { kind: "pending_result" };
}
