import Link from "next/link";
import { notFound } from "next/navigation";
import { KickoffTime } from "@/components/KickoffTime";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { TeamCrest } from "@/components/TeamCrest";
import { api, ApiError } from "@/lib/api";
import { matchState } from "@/lib/matchState";

export default async function MatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const matchId = Number(id);
  if (!Number.isFinite(matchId)) notFound();

  const match = await api.match(matchId).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  if (!match) notFound();

  const state = matchState(match);
  const needsPrediction = state.kind === "upcoming" || state.kind === "finished";
  const prediction = needsPrediction
    ? await api.prediction(matchId).catch((e) => {
        // 503 = no validated model for this competition yet (e.g. Champions League -
        // see kickcast_api/predictions.py's explicit guard) - real, expected, not a
        // page error.
        if (e instanceof ApiError && e.status === 503) return null;
        throw e;
      })
    : null;

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">
        {match.round} &middot; <KickoffTime date={match.date} kickoff={match.kickoff} />
        {state.kind === "in_progress" && (
          <span className="ml-2 inline-flex items-center gap-1.5 text-success">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            In progress &middot; updated {Math.max(0, Math.round(state.minutesSinceKickoff))}m ago
          </span>
        )}
        {state.kind === "pending_result" && <span className="ml-2 text-muted-2">Full time, score pending</span>}
      </p>

      <div className="flex flex-wrap items-center justify-center gap-4 rounded-xl border border-border bg-surface px-4 py-8 sm:gap-6">
        <TeamLink id={match.home_team.id} name={match.home_team.name} />
        {state.kind === "finished" ? (
          <span className="shrink-0 text-3xl font-bold tabular-nums text-foreground">
            {match.home_goals} &ndash; {match.away_goals}
          </span>
        ) : (
          <span className="shrink-0 text-sm font-medium uppercase tracking-wide text-muted-2">vs</span>
        )}
        <TeamLink id={match.away_team.id} name={match.away_team.name} />
      </div>

      {state.kind === "upcoming" && (
        <section className="rounded-xl border border-border bg-surface p-5 sm:p-6">
          <h2 className="mb-4 text-lg font-semibold text-foreground">Prediction</h2>
          {prediction ? (
            <>
              <div className="mx-auto max-w-md">
                <ProbabilityBar
                  size="lg"
                  home={prediction.probabilities.home}
                  draw={prediction.probabilities.draw}
                  away={prediction.probabilities.away}
                  homeLabel={match.home_team.name}
                  awayLabel={match.away_team.name}
                />
              </div>
              <div className="mt-6 grid grid-cols-2 gap-4 rounded-lg border border-border bg-surface-raised p-4 text-sm sm:grid-cols-4">
                <Stat label="Expected goals" value={`${prediction.expected_goals.home.toFixed(2)} - ${prediction.expected_goals.away.toFixed(2)}`} />
                <Stat label="Both teams to score" value={`${Math.round(prediction.btts * 100)}%`} />
                <Stat label="Over 2.5 goals" value={`${Math.round((prediction.totals["over_2.5"] ?? 0) * 100)}%`} />
                <Stat label="Evidence tier" value={prediction.evidence} />
              </div>
              <div className="mt-5">
                <h3 className="mb-2 text-sm font-medium text-muted">Likely scorelines</h3>
                <div className="flex flex-wrap gap-2">
                  {prediction.likely_scorelines.map((s) => (
                    <span key={s.score} className="rounded-md border border-border bg-surface-raised px-2.5 py-1 text-xs text-foreground">
                      {s.score} <span className="text-muted-2">({Math.round(s.prob * 100)}%)</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-5">
                <h3 className="mb-2 text-sm font-medium text-muted">Chance of a goal, by window</h3>
                <div className="flex items-end gap-1.5">
                  {prediction.goal_timing.map((w) => (
                    <div key={w.window} className="flex-1 text-center">
                      <div
                        className="mx-auto w-full rounded-t bg-gradient-to-t from-accent to-accent-hover"
                        style={{ height: `${Math.max(4, w.prob_at_least_one_goal * 80)}px` }}
                        title={`${w.window}': ${Math.round(w.prob_at_least_one_goal * 100)}% chance of a goal`}
                      />
                      <p className="mt-1.5 text-[10px] text-muted-2">{w.window}</p>
                    </div>
                  ))}
                </div>
              </div>

              {prediction.likely_scorers.available ? (
                <div className="mt-5">
                  <h3 className="mb-1 text-sm font-medium text-muted">Likely goalscorers</h3>
                  <p className="mb-3 text-[11px] text-muted-2">{prediction.likely_scorers.method}</p>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <ScorerList label={match.home_team.name} scorers={prediction.likely_scorers.home} />
                    <ScorerList label={match.away_team.name} scorers={prediction.likely_scorers.away} />
                  </div>
                </div>
              ) : (
                <p className="mt-5 text-xs text-muted-2">Likely goalscorers: not available &mdash; {prediction.likely_scorers.reason}</p>
              )}

              {prediction.cards.available && prediction.cards.home && prediction.cards.away ? (
                <div className="mt-5">
                  <h3 className="mb-2 text-sm font-medium text-muted">Expected cards</h3>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border border-border bg-surface-raised p-3 text-xs text-foreground">
                      {match.home_team.name}: {prediction.cards.home.expected_yellow.toFixed(2)} yellow,{" "}
                      {prediction.cards.home.expected_red.toFixed(3)} red
                    </div>
                    <div className="rounded-lg border border-border bg-surface-raised p-3 text-xs text-foreground">
                      {match.away_team.name}: {prediction.cards.away.expected_yellow.toFixed(2)} yellow,{" "}
                      {prediction.cards.away.expected_red.toFixed(3)} red
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-5 text-xs text-muted-2">Expected cards: not available &mdash; {prediction.cards.reason}</p>
              )}

              <p className="mt-5 text-xs text-muted-2">
                as of {prediction.as_of} &middot; {prediction.model_version} &middot; trained on{" "}
                {prediction.train_matches.total} matches ({prediction.train_matches.home} for{" "}
                {match.home_team.name}, {prediction.train_matches.away} for {match.away_team.name})
              </p>
            </>
          ) : (
            <p className="text-sm text-muted">
              Not enough finished-match history for this competition yet to fit a prediction model.
            </p>
          )}
        </section>
      )}

      {state.kind === "finished" && (
        <section className="rounded-xl border border-border bg-surface p-5">
          <h2 className="mb-2 text-lg font-semibold text-foreground">Result</h2>
          <p className="text-sm text-muted">
            Full time {match.home_goals} &ndash; {match.away_goals}.
          </p>
          {match.goal_events && match.goal_events.length > 0 ? (
            <ul className="mt-3 space-y-1.5">
              {match.goal_events.map((e, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="w-9 shrink-0 tabular-nums text-muted-2">{e.minute != null ? `${e.minute}'` : ""}</span>
                  <span className="text-foreground">
                    {e.scorer}
                    {e.own_goal ? " (own goal)" : e.penalty ? " (pen.)" : ""}
                    {" "}&mdash;{" "}
                    {e.team_id === match.home_team.id ? match.home_team.name : match.away_team.name}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-2">
              Goal scorers/minutes aren&apos;t on record for this match.
            </p>
          )}
          {prediction && (
            <p className="mt-4 border-t border-border pt-3 text-xs text-muted-2">
              Pre-match prediction: {match.home_team.name} {Math.round(prediction.probabilities.home * 100)}%, draw{" "}
              {Math.round(prediction.probabilities.draw * 100)}%, {match.away_team.name}{" "}
              {Math.round(prediction.probabilities.away * 100)}% (evidence tier {prediction.evidence})
            </p>
          )}
        </section>
      )}

      <p className="text-xs text-muted-2">source: {match.source}</p>
    </div>
  );
}

function TeamLink({ id, name }: { id: string; name: string }) {
  return (
    <Link href={`/teams/${encodeURIComponent(id)}`} className="flex w-28 flex-col items-center gap-2 text-center sm:w-36">
      <TeamCrest name={name} size="lg" />
      <span className="text-sm font-semibold text-foreground hover:text-accent sm:text-base">{name}</span>
    </Link>
  );
}

function ScorerList({
  label,
  scorers,
}: {
  label: string;
  scorers: { player: string; prob_scores: number }[];
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-raised p-3">
      <p className="mb-2 text-xs font-medium text-muted">{label}</p>
      {scorers.length === 0 ? (
        <p className="text-xs text-muted-2">no scoring history in the lookback window</p>
      ) : (
        <ul className="space-y-1.5">
          {scorers.map((s) => (
            <li key={s.player} className="flex justify-between text-xs text-foreground">
              <span>{s.player}</span>
              <span className="text-muted-2">{Math.round(s.prob_scores * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-2">{label}</p>
      <p className="mt-0.5 text-base font-semibold text-foreground">{value}</p>
    </div>
  );
}
