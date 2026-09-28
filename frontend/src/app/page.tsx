import { MatchRow } from "@/components/MatchRow";
import { api, type League, type Match, type PredictionSummary } from "@/lib/api";
import { formatShortDate } from "@/lib/time";

const MIN_MATCHES_BEFORE_WIDENING = 10;
const WIDE_WINDOW_DAYS = 14;

function collectUpcoming(fixturesByLeague: Record<string, Match[]>): Match[] {
  return Object.values(fixturesByLeague)
    .flat()
    .sort((a, b) => `${a.date}${a.kickoff ?? ""}`.localeCompare(`${b.date}${b.kickoff ?? ""}`))
    .slice(0, 20);
}

export default async function HomePage() {
  const leagues = await api.leagues();
  const byCode = new Map<string, League>(leagues.map((l) => [l.code, l]));
  const codes = leagues.map((l) => l.code);

  // Both fixture fetches and the prediction fetch are single batched requests (see
  // kickcast_api/routes/batch.py) rather than one call per league / one call per candidate
  // match - the earlier fan-out (~28 concurrent requests for one page load) was exhausting
  // the backend's connection pool.
  let fixturesByLeague = await api.fixturesByLeagues(codes, "scheduled", 50, 7).catch(() => ({}) as Record<string, Match[]>);
  let upcoming = collectUpcoming(fixturesByLeague);

  // A plain 7-day window goes thin during an international break (domestic leagues pause,
  // so the only thing left is Nations League/friendlies) - widen to 14 days rather than
  // show a near-empty homepage.
  if (upcoming.length < MIN_MATCHES_BEFORE_WIDENING) {
    fixturesByLeague = await api.fixturesByLeagues(codes, "scheduled", 50, WIDE_WINDOW_DAYS).catch(() => fixturesByLeague);
    upcoming = collectUpcoming(fixturesByLeague);
  }

  const hasDomesticMatch = upcoming.some((m) => byCode.get(m.league_code)?.kind === "domestic_league");
  let breakNote: string | null = null;
  if (!hasDomesticMatch) {
    const next = await api.nextDomesticFixtureDate().catch(() => ({ date: null }));
    if (next.date) {
      breakNote = `International break: club football resumes ${formatShortDate(next.date)}`;
    }
  }

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
        {breakNote && (
          <p className="mt-3 inline-flex items-center gap-2 rounded-full border border-warning/30 bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning">
            {breakNote}
          </p>
        )}
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
