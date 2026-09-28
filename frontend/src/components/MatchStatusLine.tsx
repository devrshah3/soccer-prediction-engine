import { timeAgo } from "@/lib/time";
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
      {state.score && state.updatedAt && (
        // Relative to the render clock, so it may differ by a minute between server and client.
        <p className="mt-0.5 text-[11px] text-muted-2" suppressHydrationWarning>
          {scoreUpdatedLabel(state.updatedAt)}
        </p>
      )}
    </div>
  );
}

function scoreUpdatedLabel(iso: string): string {
  const ago = timeAgo(iso); // "just now" | "updated 3m ago" | ...
  return ago === "just now" ? "score updated just now" : `score ${ago}`;
}
