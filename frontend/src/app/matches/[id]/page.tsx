import Link from "next/link";
import { notFound } from "next/navigation";
import { KickoffTime } from "@/components/KickoffTime";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { api, ApiError } from "@/lib/api";

export default async function MatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const matchId = Number(id);
  if (!Number.isFinite(matchId)) notFound();

  const match = await api.match(matchId).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  if (!match) notFound();

  const prediction = match.status === "scheduled" ? await api.prediction(matchId) : null;

  return (
    <div className="space-y-6">
      <p className="text-sm text-zinc-500">
        {match.round} &middot; <KickoffTime date={match.date} kickoff={match.kickoff} />
      </p>

      <div className="flex items-center justify-center gap-6 py-4">
        <TeamLink id={match.home_team.id} name={match.home_team.name} />
        {match.status === "finished" ? (
          <span className="text-3xl font-bold text-zinc-50">
            {match.home_goals} - {match.away_goals}
          </span>
        ) : (
          <span className="text-lg text-zinc-500">vs</span>
        )}
        <TeamLink id={match.away_team.id} name={match.away_team.name} />
      </div>

      {match.status === "scheduled" && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
          <h2 className="mb-3 text-lg font-semibold text-zinc-200">Prediction</h2>
          {prediction ? (
            <>
              <ProbabilityBar
                home={prediction.probabilities.home}
                draw={prediction.probabilities.draw}
                away={prediction.probabilities.away}
                homeLabel={match.home_team.name}
                awayLabel={match.away_team.name}
              />
              <div className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <Stat label="Expected goals" value={`${prediction.expected_goals.home.toFixed(2)} - ${prediction.expected_goals.away.toFixed(2)}`} />
                <Stat label="Both teams to score" value={`${Math.round(prediction.btts * 100)}%`} />
                <Stat label="Over 2.5 goals" value={`${Math.round((prediction.totals["over_2.5"] ?? 0) * 100)}%`} />
                <Stat label="Evidence tier" value={prediction.evidence} />
              </div>
              <div className="mt-4">
                <h3 className="mb-2 text-sm font-medium text-zinc-400">Likely scorelines</h3>
                <div className="flex flex-wrap gap-2">
                  {prediction.likely_scorelines.map((s) => (
                    <span key={s.score} className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-300">
                      {s.score} <span className="text-zinc-500">({Math.round(s.prob * 100)}%)</span>
                    </span>
                  ))}
                </div>
              </div>
              <p className="mt-4 text-xs text-zinc-500">
                as of {prediction.as_of} &middot; {prediction.model_version} &middot; trained on{" "}
                {prediction.train_matches.total} matches ({prediction.train_matches.home} for{" "}
                {match.home_team.name}, {prediction.train_matches.away} for {match.away_team.name})
              </p>
            </>
          ) : (
            <p className="text-sm text-zinc-500">
              Not enough finished-match history for this competition yet to fit a prediction model.
            </p>
          )}
        </section>
      )}

      {match.status === "finished" && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
          <h2 className="mb-2 text-lg font-semibold text-zinc-200">Result</h2>
          <p className="text-sm text-zinc-500">
            Full time {match.home_goals} - {match.away_goals}. Goal scorers/minutes and an official
            highlights link aren&apos;t available yet - see MORNING_REPORT.md.
          </p>
        </section>
      )}

      <p className="text-xs text-zinc-600">source: {match.source}</p>
    </div>
  );
}

function TeamLink({ id, name }: { id: string; name: string }) {
  return (
    <Link href={`/teams/${encodeURIComponent(id)}`} className="text-xl font-semibold text-zinc-100 hover:text-emerald-400">
      {name}
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="text-base font-semibold text-zinc-100">{value}</p>
    </div>
  );
}
