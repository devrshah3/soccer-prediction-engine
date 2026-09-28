import Link from "next/link";
import type { ReplayMatch } from "@/lib/api";
import { LeagueChip } from "./LeagueChip";
import { TeamCrest } from "./TeamCrest";

type Outcome = "home" | "draw" | "away";

function outcomeLabel(outcome: Outcome, home: string, away: string): string {
  return outcome === "draw" ? "a draw" : `${outcome === "home" ? home : away} win`;
}

// One finished (or not-yet-resulted) match from yesterday: score, a glass timeline of the
// real events we actually have, the pre-match-prediction-vs-result chip, and a recap written
// only from verified facts. Nothing here is invented - when a source has no events for a
// match, the card says so plainly instead of filling the space.
export function ReplayMatchCard({ match, noEventsNote }: { match: ReplayMatch; noEventsNote: string }) {
  const home = match.home_team.name;
  const away = match.away_team.name;
  const pr = match.prediction_result;

  return (
    <article className="glass p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <LeagueChip name={match.league_name} country={match.league_country} />
        <span className="text-xs text-muted">
          {match.round ? `${match.round} · ` : ""}
          {match.kickoff ? `${match.kickoff} UTC` : match.date}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <TeamCrest name={home} />
          <span className="truncate text-sm font-medium text-foreground sm:text-base">{home}</span>
        </div>
        {match.has_result ? (
          <span className="shrink-0 rounded-lg bg-white/10 px-3 py-1.5 text-lg font-bold tabular-nums text-foreground ring-1 ring-inset ring-white/15">
            {match.home_goals} &ndash; {match.away_goals}
          </span>
        ) : (
          <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-muted-2">vs</span>
        )}
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2.5">
          <span className="truncate text-right text-sm font-medium text-foreground sm:text-base">{away}</span>
          <TeamCrest name={away} />
        </div>
      </div>

      {!match.has_result && (
        <p className="mt-3 rounded-lg bg-white/[0.06] px-3 py-2 text-xs text-muted">
          Result not available yet &mdash; it hasn&apos;t reached our data sources.
        </p>
      )}

      {pr && (
        <p
          className={`mt-3 inline-flex flex-wrap items-center gap-x-2 rounded-full px-3 py-1 text-xs font-medium ${
            pr.correct ? "bg-accent-soft text-accent" : "bg-white/10 text-muted"
          }`}
        >
          <span>{pr.correct ? "Prediction called it" : "Prediction missed"}</span>
          <span className="text-muted-2">
            &middot; favoured {outcomeLabel(pr.predicted, home, away)} ({Math.round(pr.predicted_probability * 100)}%),
            got {outcomeLabel(pr.actual, home, away)} ({Math.round(pr.actual_probability * 100)}%)
          </span>
        </p>
      )}
      {match.has_result && !pr && <p className="mt-3 text-xs text-muted-2">No pre-match prediction on record for this match.</p>}

      {match.has_result && (
        <div className="mt-4">
          {match.events.length > 0 ? (
            <ol className="space-y-1.5" aria-label="Match events">
              {match.events.map((e, i) => (
                <li key={`${e.player}-${e.minute}-${i}`} className="glass-row flex items-center gap-3 px-3 py-2 text-sm">
                  <span className="w-10 shrink-0 tabular-nums text-muted-2">{e.minute != null ? `${e.minute}'` : "–"}</span>
                  <span className="min-w-0 flex-1 truncate text-foreground">
                    {e.player} <span className="text-muted-2">({e.team_name})</span>
                  </span>
                  {(e.penalty || e.own_goal) && (
                    <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                      {e.own_goal ? "Own goal" : "Penalty"}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          ) : match.events_status === "complete" ? (
            <p className="text-xs text-muted-2">Neither team scored.</p>
          ) : null}
          {match.events_status === "partial" && (
            <p className="mt-2 text-xs text-muted-2">
              Only {match.events.length} of {(match.home_goals ?? 0) + (match.away_goals ?? 0)} goals have a recorded
              scorer. Cards and substitutions aren&apos;t available from our free data sources.
            </p>
          )}
          {match.events_status === "none" && <p className="text-xs text-muted-2">{noEventsNote}</p>}
        </div>
      )}

      {match.has_result && (
        <div className="mt-4 border-t border-white/10 pt-3">
          <p className="text-sm text-muted">{match.recap.text}</p>
          <p className="mt-1.5 text-[11px] text-muted-2">{match.recap.label}</p>
        </div>
      )}

      <Link href={`/matches/${match.id}`} className="mt-3 inline-block text-xs font-medium text-accent hover:underline">
        Full match page &rarr;
      </Link>
    </article>
  );
}
