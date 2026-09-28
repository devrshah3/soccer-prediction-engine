import type { MatchState } from "@/lib/matchState";

// Caption shown under a prediction bar during a live match, so it's clear the odds are the
// pre-match ones and are not updating in-game.
export const PRE_MATCH_CAPTION = "Pre-match prediction · not updating live";

// One status block for every surface that renders a match (cards, match page, team page).
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
  // Only the provider's own live flag earns the provider's clock; otherwise it's the
  // elapsed-time-since-kickoff fallback and we say so plainly.
  const label = state.providerLive && state.providerMinute != null ? `Live · ${state.providerMinute}'` : `Live · kickoff ${elapsed} min ago`;
  return (
    <div className={className}>
      <p className="flex items-center gap-1.5 text-xs font-medium text-success">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
        {label}
      </p>
      {!state.score && <p className="mt-0.5 text-xs text-muted-2">No live score available</p>}
      {state.updatedAt && (
        // Our own last-fetch time, not the match clock - we are NOT real-time. Relative to the
        // render clock, so server and client may differ by a minute.
        <p className="mt-0.5 text-[11px] text-muted-2" suppressHydrationWarning>
          {updatedLabel(state.updatedAt)}
        </p>
      )}
    </div>
  );
}

export function updatedLabel(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "Updated recently";
  const min = Math.max(0, Math.round((now - t) / 60000));
  if (min < 1) return "Updated just now";
  if (min < 60) return `Updated ${min} min ago`;
  return `Updated ${Math.round(min / 60)} h ago`;
}

// Shown on the match page while a match is live: the honest cadence, next to the score.
export function ScoreCadenceNote() {
  return <p className="text-xs text-muted-2">Scores update roughly every 10 minutes, not instantly.</p>;
}
