import { matchState } from "./matchState";

// B.5: "today" is done and should roll over to the next matchday once every one of
// today's matches is Finished - an explicit source flag, or matchState's last-resort
// 150-minute fallback. A match still "scheduled" or "live" keeps today active. A day with no matches at all also
// counts as settled - there's nothing to roll away from.
export function isTodaySettled(todaysMatches: Parameters<typeof matchState>[0][], now: Date = new Date()): boolean {
  if (todaysMatches.length === 0) return true;
  return todaysMatches.every((m) => {
    const state = matchState(m, now);
    return state.kind === "finished";
  });
}
