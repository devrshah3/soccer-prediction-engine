import type { Match } from "./api";
import { matchState } from "./matchState";

// B.5: "today" is done and should roll over to the next matchday once every one of
// today's matches is settled - finished, or kickoff has passed and it's been long enough
// (matchState's 135-minute window) that no score is coming without a real update. A
// match still "upcoming" (hasn't kicked off) or "in_progress" (kicked off recently, no
// score yet) keeps today active. A day with no matches at all also counts as settled -
// there's nothing to roll away from.
export function isTodaySettled(todaysMatches: Pick<Match, "status" | "date" | "kickoff">[], now: Date = new Date()): boolean {
  if (todaysMatches.length === 0) return true;
  return todaysMatches.every((m) => {
    const state = matchState(m, now);
    return state.kind === "finished" || state.kind === "pending_result";
  });
}
