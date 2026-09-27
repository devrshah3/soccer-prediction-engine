import { MatchRow } from "@/components/MatchRow";
import { api, type League, type Match } from "@/lib/api";

export default async function HomePage() {
  const leagues = await api.leagues();
  const byCode = new Map<string, League>(leagues.map((l) => [l.code, l]));

  const fixturesByLeague = await Promise.all(
    leagues.map((l) => api.leagueFixtures(l.code, "scheduled", 6).catch(() => [] as Match[]))
  );
  const upcoming = fixturesByLeague
    .flat()
    .sort((a, b) => `${a.date}${a.kickoff ?? ""}`.localeCompare(`${b.date}${b.kickoff ?? ""}`))
    .slice(0, 20);

  const predictions = await Promise.all(upcoming.map((m) => api.prediction(m.id).catch(() => null)));

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
          {upcoming.map((m, i) => (
            <MatchRow key={m.id} match={m} league={byCode.get(m.league_code)} prediction={predictions[i]} />
          ))}
        </div>
      )}
    </div>
  );
}
