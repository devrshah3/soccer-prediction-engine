import type { MatchState } from "@/lib/matchState";

// Label shown with a bar during a live match, so it's clear the odds are the pre-match
// ones and are not updating in-game.
export const PRE_MATCH_ODDS_LABEL = "Pre-match odds";

// One status line for every surface that renders a match (cards, match page, team page).
// Scheduled renders nothing; Live and Finished each say what we actually know.
export function MatchStatusLine({ state, className = "" }: { state: MatchState; className?: string }) {
  if (state.kind === "scheduled") return null;

  if (state.kind === "finished") {
    return (
      <p className={`text-xs font-medium uppercase tracking-wide text-muted-2 ${className}`}>
        {state.score ? "Full time" : "Full time, score pending"}
      </p>
    );
  }

  const elapsed = Math.max(0, Math.round(state.minutesSinceKickoff));
  // Only claim "In progress" from a real provider live flag; otherwise it's the
  // elapsed-time-since-kickoff fallback and we say so plainly.
  const label = state.providerLive ? "In progress" : `Kickoff ${elapsed} min ago`;
  return (
    <p className={`flex flex-wrap items-center gap-x-1.5 text-xs font-medium text-success ${className}`}>
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
      {state.score && (
        <span className="tabular-nums text-foreground">
          {state.score.home}&ndash;{state.score.away}
          {state.providerMinute != null ? `, ${state.providerMinute}'` : ""}
        </span>
      )}
      <span>{state.score ? `· ${label}` : label}</span>
    </p>
  );
}
