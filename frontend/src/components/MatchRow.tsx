import Link from "next/link";
import type { League, Match, PredictionSummary } from "@/lib/api";
import { matchState } from "@/lib/matchState";
import { isPredictionStale } from "@/lib/predictionFreshness";
import { KickoffTime } from "./KickoffTime";
import { LeagueChip } from "./LeagueChip";
import { PredictionInfoPopover } from "./PredictionInfoPopover";
import { ProbabilityBar } from "./ProbabilityBar";
import { TeamCrest } from "./TeamCrest";

export function MatchRow({
  match,
  league,
  prediction,
  longRange,
  dateMayChange,
}: {
  match: Match;
  league?: League;
  prediction?: PredictionSummary | null;
  longRange?: boolean;
  dateMayChange?: boolean;
}) {
  const state = matchState(match);
  const showScore = state.kind === "finished";
  const showPrediction = state.kind === "upcoming";

  return (
    <Link
      href={`/matches/${match.id}`}
      className="group block rounded-xl border border-border bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-border-strong hover:bg-surface-hover hover:shadow-lg hover:shadow-black/20"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        {league ? <LeagueChip name={league.name} country={league.country} /> : <span />}
        <span className="text-xs text-muted">
          {match.round ? <span className="mr-1.5">{match.round}</span> : null}
          <span className="text-muted-2">&middot;</span>{" "}
          <KickoffTime date={match.date} kickoff={match.kickoff} />
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <TeamCrest name={match.home_team.name} />
          <span className="truncate text-sm font-medium text-foreground">{match.home_team.name}</span>
        </div>
        {showScore ? (
          <span className="shrink-0 rounded-md bg-surface-raised px-2.5 py-1 text-sm font-bold tabular-nums text-foreground ring-1 ring-inset ring-border">
            {match.home_goals} &ndash; {match.away_goals}
          </span>
        ) : (
          <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-muted-2">vs</span>
        )}
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2.5">
          <span className="truncate text-right text-sm font-medium text-foreground">{match.away_team.name}</span>
          <TeamCrest name={match.away_team.name} />
        </div>
      </div>

      {state.kind === "finished" && (
        <p className="mt-3 text-xs font-medium uppercase tracking-wide text-muted-2">Full time</p>
      )}
      {state.kind === "in_progress" && (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-success">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
          In progress &middot; updated {Math.max(0, Math.round(state.minutesSinceKickoff))}m ago
        </p>
      )}
      {state.kind === "pending_result" && (
        <p className="mt-3 text-xs font-medium text-muted-2">Full time, score pending</p>
      )}

      {showPrediction && prediction && (
        <div className="mt-4 border-t border-border pt-3">
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <ProbabilityBar
                home={prediction.probabilities.home}
                draw={prediction.probabilities.draw}
                away={prediction.probabilities.away}
                homeLabel={match.home_team.name}
                awayLabel={match.away_team.name}
              />
            </div>
            <PredictionInfoPopover prediction={prediction} />
          </div>
          {/* D.11: cards otherwise show nothing about provenance/staleness - a warning
              only appears when it's actually justified (see isPredictionStale). */}
          {isPredictionStale(prediction.computed_at, match.date) && (
            <p className="mt-2 text-[11px] font-medium text-warning">Prediction may be outdated</p>
          )}
          {dateMayChange && <p className="mt-1 text-[11px] text-warning">Date may change</p>}
          {longRange && (
            <p className="mt-1 text-[11px] text-muted-2">
              Long-range: based on results up to {prediction.as_of}; team news and form can change.
            </p>
          )}
        </div>
      )}
      {showPrediction && !prediction && (
        <p className="mt-3 text-xs text-muted-2">prediction not available yet</p>
      )}
    </Link>
  );
}
