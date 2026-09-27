import { MatchRow } from "@/components/MatchRow";
import { api, type League, type Match, type PredictionSummary } from "@/lib/api";

export default async function HomePage() {
  const leagues = await api.leagues();
  const byCode = new Map<string, League>(leagues.map((l) => [l.code, l]));

  // Both of these are single batched requests (see kickcast_api/routes/batch.py) rather
  // than one call per league / one call per candidate match - the earlier fan-out (~28
  // concurrent requests for one page load) was exhausting the backend's connection pool.
  const fixturesByLeague = await api
    .fixturesByLeagues(leagues.map((l) => l.code), "scheduled", 6)
    .catch(() => ({}) as Record<string, Match[]>);
  const upcoming = Object.values(fixturesByLeague)
    .flat()
    .sort((a, b) => `${a.date}${a.kickoff ?? ""}`.localeCompare(`${b.date}${b.kickoff ?? ""}`))
    .slice(0, 20);

  const predictionsById = await api
    .predictionsSummary(upcoming.map((m) => m.id))
    .catch(() => ({}) as Record<string, PredictionSummary | null>);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Upcoming predictions</h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Our own model &mdash; home / draw / away probabilities, backtested out-of-sample. Not a promise of
          accuracy.
        </p>
      </div>
      {upcoming.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface/50 p-8 text-center">
          <p className="text-sm text-muted">
            No upcoming fixtures found. Has <code className="rounded bg-surface-raised px-1.5 py-0.5 text-muted-2">python scripts/ingest.py</code>{" "}
            been run against the API&apos;s database?
          </p>
        </div>
      ) : (
        <div className="grid gap-3.5 sm:grid-cols-2">
          {upcoming.map((m) => (
            <MatchRow
              key={m.id}
              match={m}
              league={byCode.get(m.league_code)}
              prediction={predictionsById[String(m.id)]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
