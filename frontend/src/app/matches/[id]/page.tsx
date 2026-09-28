import Link from "next/link";
import { notFound } from "next/navigation";
import { CardList } from "@/components/CardList";
import { GoalTimeline } from "@/components/GoalList";
import { KickoffTime } from "@/components/KickoffTime";
import { LiveAutoRefresh } from "@/components/LiveAutoRefresh";
import { MatchStatusLine } from "@/components/MatchStatusLine";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { TeamCrest } from "@/components/TeamCrest";
import { api, ApiError } from "@/lib/api";
import { matchState } from "@/lib/matchState";
import { timeAgo } from "@/lib/time";

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
  // Live keeps its (pre-match) prediction; finished shows it only as a footnote under the result.
  const prediction = await api.prediction(matchId).catch((e) => {
    // 503 = no validated model for this competition yet (e.g. Champions League -
    // see kickcast_api/predictions.py's explicit guard) - real, expected, not a
    // page error.
    if (e instanceof ApiError && e.status === 503) return null;
    throw e;
  });

  return (
    <div className="space-y-6">
      <LiveAutoRefresh active={state.kind === "live"} />
      <div className="text-sm text-muted">
        <p>
          {match.round} &middot; <KickoffTime date={match.date} kickoff={match.kickoff} />
        </p>
        <MatchStatusLine state={state} className="mt-1" />
      </div>

      <div className="flex flex-wrap items-center justify-center gap-4 glass px-4 py-8 sm:gap-6">
        <TeamLink id={match.home_team.id} name={match.home_team.name} />
        {state.kind === "finished" && state.score ? (
          <span className="shrink-0 text-3xl font-bold tabular-nums text-foreground">
            {state.score.home} &ndash; {state.score.away}
          </span>
        ) : state.kind === "live" && state.score ? (
          <span className="shrink-0 text-3xl font-bold tabular-nums text-foreground">
            {state.score.home} &ndash; {state.score.away}
          </span>
        ) : (
          <span className="shrink-0 text-sm font-medium uppercase tracking-wide text-muted-2">vs</span>
        )}
        <TeamLink id={match.away_team.id} name={match.away_team.name} />
      </div>

      {state.kind === "live" && match.goal_events && match.goal_events.length > 0 && (
        <section className="glass p-5">
          <h2 className="text-lg font-semibold text-foreground">Goals</h2>
          <GoalTimeline goals={match.goal_events} home={match.home_team} away={match.away_team} />
        </section>
      )}

      {state.kind !== "finished" && (
        <section className="glass p-5 sm:p-6">
          <h2 className="mb-1 text-lg font-semibold text-foreground">
            {state.kind === "live" ? "Pre-match prediction" : "Prediction"}
          </h2>
          {state.kind === "live" && <p className="mb-4 text-xs text-muted-2">Not updating live.</p>}
          {state.kind !== "live" && <div className="mb-3" />}
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
              <div className="mt-6 grid grid-cols-2 gap-4 glass-row p-4 text-sm sm:grid-cols-4">
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
                      {s.score} <span className="text-muted">({Math.round(s.prob * 100)}%)</span>
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
                    <div className="glass-row p-3 text-xs text-foreground">
                      {match.home_team.name}: {prediction.cards.home.expected_yellow.toFixed(2)} yellow,{" "}
                      {prediction.cards.home.expected_red.toFixed(3)} red
                    </div>
                    <div className="glass-row p-3 text-xs text-foreground">
                      {match.away_team.name}: {prediction.cards.away.expected_yellow.toFixed(2)} yellow,{" "}
                      {prediction.cards.away.expected_red.toFixed(3)} red
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-5 text-xs text-muted-2">Expected cards: not available &mdash; {prediction.cards.reason}</p>
              )}

              <details className="mt-5 glass-row p-3 text-xs text-muted-2">
                <summary className="cursor-pointer select-none font-medium text-muted">Prediction details</summary>
                <p className="mt-2">
                  {prediction.computed_at ? `${timeAgo(prediction.computed_at)} · ` : ""}
                  data cutoff {prediction.as_of} &middot; {prediction.model_version} &middot; trained on{" "}
                  {prediction.train_matches.total} matches ({prediction.train_matches.home} for{" "}
                  {match.home_team.name}, {prediction.train_matches.away} for {match.away_team.name})
                </p>
              </details>
            </>
          ) : (
            <p className="text-sm text-muted">
              Not enough finished-match history for this competition yet to fit a prediction model.
            </p>
          )}
        </section>
      )}

      {state.kind === "finished" && (
        <section className="glass p-5">
          <h2 className="mb-2 text-lg font-semibold text-foreground">Result</h2>
          <p className="text-sm text-muted">
            {state.score ? (
              <>Full time {state.score.home} &ndash; {state.score.away}.</>
            ) : (
              <>Full time, score pending.</>
            )}
          </p>
          <GoalTimeline goals={match.goal_events} home={match.home_team} away={match.away_team} />
          {prediction && (
            <p className="mt-4 border-t border-border pt-3 text-xs text-muted-2">
              Pre-match prediction: {match.home_team.name} {Math.round(prediction.probabilities.home * 100)}%, draw{" "}
              {Math.round(prediction.probabilities.draw * 100)}%, {match.away_team.name}{" "}
              {Math.round(prediction.probabilities.away * 100)}% (evidence tier {prediction.evidence})
            </p>
          )}
        </section>
      )}

      {state.kind !== "scheduled" && (
        <CardList cards={match.card_events} home={match.home_team} away={match.away_team} />
      )}

      <p className="text-xs text-muted-2">source: {match.source}</p>
    </div>
  );
}

function TeamLink({ id, name }: { id: string; name: string }) {
  return (
    <Link href={`/teams/${encodeURIComponent(id)}`} className="flex w-28 flex-col items-center gap-2 text-center sm:w-36">
      <TeamCrest name={name} size="lg" />
      <span className="text-sm font-semibold text-foreground hover:text-accent-text sm:text-base">{name}</span>
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
    <div className="glass-row p-3">
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
