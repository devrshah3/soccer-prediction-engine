import Link from "next/link";
import { DateMatchList } from "@/components/DateMatchList";
import { DatePicker } from "@/components/DatePicker";
import { MatchRow } from "@/components/MatchRow";
import { api, type League, type Match, type MatchOnDate, type PredictionSummary } from "@/lib/api";
import { matchState } from "@/lib/matchState";
import { isTodaySettled } from "@/lib/rollover";
import { formatShortDate } from "@/lib/time";

const MIN_MATCHES_BEFORE_WIDENING = 10;
const WIDE_WINDOW_DAYS = 14;

function isoDaysFromToday(offset: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

function collectUpcoming(fixturesByLeague: Record<string, Match[]>): Match[] {
  return Object.values(fixturesByLeague)
    .flat()
    .sort((a, b) => `${a.date}${a.kickoff ?? ""}`.localeCompare(`${b.date}${b.kickoff ?? ""}`))
    .slice(0, 20);
}

// B.5's rollover decision and B.7's section layout only apply to the implicit "today"
// view; an explicitly-picked date (B.6) gets the simpler grouped-by-competition view.
// "Today" here is the server's UTC date - a real, known simplification (no per-viewer
// timezone signal is available server-side without a client round trip); B.6's date
// grouping utility (src/lib/localDate.ts) is unit-tested for the real day-boundary case
// this would need to fully account for a viewer whose local date differs from UTC's.
export default async function HomePage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const { date } = await searchParams;
  const today = isoDaysFromToday(0);
  const leagues = await api.leagues();
  const byCode = new Map<string, League>(leagues.map((l) => [l.code, l]));

  if (date && date !== today) {
    return <SelectedDatePage date={date} leagues={byCode} />;
  }
  return <DefaultHomePage today={today} leagues={byCode} />;
}

async function SelectedDatePage({ date, leagues }: { date: string; leagues: Map<string, League> }) {
  const matches = await api.matchesByDate(date).catch(() => [] as MatchOnDate[]);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Matches</h1>
        <p className="mt-1 text-sm text-muted">{formatShortDate(date)}</p>
        <div className="mt-4">
          <DatePicker selected={date} />
        </div>
      </div>
      {matches.length === 0 ? <EmptyDate date={date} /> : <DateMatchList matches={matches} leagues={leagues} />}
    </div>
  );
}

async function EmptyDate({ date }: { date: string }) {
  const nearby = await api.nearbyMatchDate(date, "nearest").catch(() => ({ date: null }));
  return (
    <div className="rounded-xl border border-dashed border-border-strong bg-surface/50 p-8 text-center">
      <p className="text-sm text-muted">No matches on this date.</p>
      {nearby.date && (
        <Link href={`/?date=${nearby.date}`} className="mt-2 inline-block text-sm text-accent hover:underline">
          Go to {formatShortDate(nearby.date)}, the nearest date with matches &rarr;
        </Link>
      )}
    </div>
  );
}

async function DefaultHomePage({ today, leagues }: { today: string; leagues: Map<string, League> }) {
  const codes = [...leagues.keys()];

  // --- Today (B.7): live/finished first, then still to play. Once nothing is left to
  // play - decided at read time from the current clock, see rollover.ts - automatically
  // show the next matchday's full predictions instead (B.5).
  const todaysMatches = await api.matchesByDate(today).catch(() => [] as MatchOnDate[]);
  const settled = isTodaySettled(todaysMatches);
  let rolledOverDate: string | null = null;
  let rolledOverMatches: MatchOnDate[] = [];
  if (settled) {
    const nearby = await api.nearbyMatchDate(today, "forward").catch(() => ({ date: null }));
    if (nearby.date) {
      rolledOverDate = nearby.date;
      rolledOverMatches = await api.matchesByDate(nearby.date).catch(() => [] as MatchOnDate[]);
    }
  }
  const todaySorted = [...todaysMatches].sort((a, b) => {
    const rank = (m: MatchOnDate) => {
      const s = matchState(m).kind;
      return s === "in_progress" ? 0 : s === "finished" || s === "pending_result" ? 1 : 2;
    };
    return rank(a) - rank(b) || (a.kickoff ?? "").localeCompare(b.kickoff ?? "");
  });

  // --- Next 7 days (extend to 14 if thin; international-break note) - unchanged from A4.
  let fixturesByLeague = await api.fixturesByLeagues(codes, "scheduled", 50, 7).catch(() => ({}) as Record<string, Match[]>);
  let upcoming = collectUpcoming(fixturesByLeague);
  if (upcoming.length < MIN_MATCHES_BEFORE_WIDENING) {
    fixturesByLeague = await api.fixturesByLeagues(codes, "scheduled", 50, WIDE_WINDOW_DAYS).catch(() => fixturesByLeague);
    upcoming = collectUpcoming(fixturesByLeague);
  }
  const hasDomesticMatch = upcoming.some((m) => leagues.get(m.league_code)?.kind === "domestic_league");
  let breakNote: string | null = null;
  if (!hasDomesticMatch) {
    const next = await api.nextDomesticFixtureDate().catch(() => ({ date: null }));
    if (next.date) breakNote = `International break: club football resumes ${formatShortDate(next.date)}`;
  }
  const predictionsById = await api
    .predictionsSummary(upcoming.map((m) => m.id))
    .catch(() => ({}) as Record<string, PredictionSummary | null>);

  // --- Recent results (B.7): the 3 days before today, results only.
  const recentDates = [1, 2, 3].map((n) => isoDaysFromToday(-n));
  const recentByDate = await Promise.all(recentDates.map((d) => api.matchesByDate(d).catch(() => [] as MatchOnDate[])));
  const recentResults = recentByDate
    .flat()
    .filter((m) => m.status === "finished")
    .sort((a, b) => `${b.date}${b.kickoff ?? ""}`.localeCompare(`${a.date}${a.kickoff ?? ""}`));

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">KickCast</h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Our own model &mdash; home / draw / away probabilities, backtested out-of-sample. Not a promise of
          accuracy.
        </p>
        <div className="mt-4">
          <DatePicker selected={today} />
        </div>
      </div>

      <section>
        <h2 className="mb-4 text-xl font-bold tracking-tight text-foreground">
          {rolledOverDate ? `Next matchday: ${formatShortDate(rolledOverDate)}` : "Today"}
        </h2>
        {rolledOverDate ? (
          rolledOverMatches.length === 0 ? (
            <p className="text-sm text-muted">Nothing scheduled yet.</p>
          ) : (
            <DateMatchList matches={rolledOverMatches} leagues={leagues} />
          )
        ) : todaySorted.length === 0 ? (
          <p className="text-sm text-muted">No matches today.</p>
        ) : (
          <DateMatchList matches={todaySorted} leagues={leagues} />
        )}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold tracking-tight text-foreground">Next 7 days</h2>
          {breakNote && (
            <p className="inline-flex items-center gap-2 rounded-full border border-warning/30 bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning">
              {breakNote}
            </p>
          )}
        </div>
        {upcoming.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-strong bg-surface/50 p-8 text-center">
            <p className="text-sm text-muted">
              No upcoming fixtures found. Has{" "}
              <code className="rounded bg-surface-raised px-1.5 py-0.5 text-muted-2">python scripts/ingest.py</code>{" "}
              been run against the API&apos;s database?
            </p>
          </div>
        ) : (
          <div className="grid gap-3.5 sm:grid-cols-2">
            {upcoming.map((m) => (
              <MatchRow
                key={m.id}
                match={m}
                league={leagues.get(m.league_code)}
                prediction={predictionsById[String(m.id)]}
              />
            ))}
          </div>
        )}
      </section>

      {recentResults.length > 0 && (
        <section>
          <h2 className="mb-4 text-xl font-bold tracking-tight text-foreground">Recent results</h2>
          <div className="grid gap-3.5 sm:grid-cols-2">
            {recentResults.map((m) => (
              <MatchRow key={m.id} match={m} league={leagues.get(m.league_code)} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
