import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { DateMatchList } from "@/components/DateMatchList";
import { DatePicker } from "@/components/DatePicker";
import { Flag } from "@/components/Flag";
import { LeagueTableSheet } from "@/components/LeagueTableSheet";
import { SeasonSelect } from "@/components/SeasonSelect";
import { api, ApiError, type League, type MatchOnDate } from "@/lib/api";
import { legacyCodeRedirect, SLUG_TO_CODE } from "@/lib/leagueSlugs";
import { isTodaySettled } from "@/lib/rollover";
import { matchState } from "@/lib/matchState";
import { formatShortDate } from "@/lib/time";

function isoDaysFromToday(offset: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ season?: string; date?: string; view?: string }>;
}) {
  const { slug } = await params;
  const { season, date, view } = await searchParams;

  // Old code-based URL (e.g. /leagues/en.1) -> the clean slug, permanently.
  const cleanSlug = legacyCodeRedirect(slug);
  if (cleanSlug) {
    const qs = new URLSearchParams();
    if (season) qs.set("season", season);
    if (date) qs.set("date", date);
    if (view) qs.set("view", view);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    permanentRedirect(`/leagues/${cleanSlug}${suffix}`);
  }
  const code = SLUG_TO_CODE[slug];
  if (!code) notFound();

  const leagues = await api.leagues();
  const league = leagues.find((l) => l.code === code);
  if (!league) notFound();

  const standings = await api.standings(code, season).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  // A table failing to compute (e.g. a season with no processed results yet) is a real,
  // honest state - the page still renders (fixtures/history), it just has no table/Sheet.
  const hasTable = !!standings && standings.table.length > 0;
  const isCurrentSeason = !season || (standings && season === standings.available_seasons[0]);

  const trophyOdds =
    standings && isCurrentSeason
      ? await api.trophyOdds(code, standings.season).catch((e) => {
          if (e instanceof ApiError && e.status === 503) return null;
          throw e;
        })
      : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Flag country={league.country} className="h-8 w-11 shrink-0 rounded-md" />
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{league.name}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {standings && standings.available_seasons.length > 1 && (
            <SeasonSelect basePath={`/leagues/${slug}`} season={standings.season} seasons={standings.available_seasons} />
          )}
          {hasTable && standings && (
            <LeagueTableSheet
              leagueName={league.name}
              standings={standings}
              trophyOdds={trophyOdds}
              showZoneMarkers={league.kind === "domestic_league"}
              initialOpen={view === "table"}
            />
          )}
        </div>
      </div>

      {isCurrentSeason ? (
        <CurrentSeasonView code={code} date={date} slug={slug} league={league} />
      ) : (
        <PastSeasonView code={code} standings={standings} />
      )}
    </div>
  );
}

async function CurrentSeasonView({
  code,
  date,
  slug,
  league,
}: {
  code: string;
  date?: string;
  slug: string;
  league: League;
}) {
  const today = isoDaysFromToday(0);
  const basePath = `/leagues/${slug}`;

  if (date && date !== today) {
    const matches = await api.matchesByDate(date, code).catch(() => [] as MatchOnDate[]);
    return (
      <div className="space-y-6">
        <DatePicker selected={date} basePath={basePath} />
        {matches.length === 0 ? (
          <div className="glass border-dashed p-8 text-center">
            <p className="text-sm text-muted">No {league.name} matches on this date.</p>
          </div>
        ) : (
          <DateMatchList matches={matches} leagues={new Map([[code, league]])} />
        )}
      </div>
    );
  }

  const todaysMatches = await api.matchesByDate(today, code).catch(() => [] as MatchOnDate[]);
  const settled = isTodaySettled(todaysMatches);
  let rolledOverDate: string | null = null;
  let rolledOverMatches: MatchOnDate[] = [];
  if (settled) {
    // Scoped rollover: the next real scheduled fixture date for THIS league specifically
    // (api.leagueFixtures, not the global nearby-date lookup, which isn't league-scoped).
    const next = await api.leagueFixtures(code, "scheduled", 1).catch(() => []);
    if (next[0]) {
      rolledOverDate = next[0].date;
      rolledOverMatches = await api.matchesByDate(rolledOverDate, code).catch(() => [] as MatchOnDate[]);
    }
  }
  const todaySorted = [...todaysMatches].sort((a, b) => {
    const rank = (m: MatchOnDate) => {
      const s = matchState(m).kind;
      return s === "in_progress" ? 0 : s === "finished" || s === "pending_result" ? 1 : 2;
    };
    return rank(a) - rank(b) || (a.kickoff ?? "").localeCompare(b.kickoff ?? "");
  });

  const recentDates = [1, 2, 3].map((n) => isoDaysFromToday(-n));
  const recentByDate = await Promise.all(recentDates.map((d) => api.matchesByDate(d, code).catch(() => [] as MatchOnDate[])));
  const recentResults = recentByDate
    .flat()
    .filter((m) => m.status === "finished")
    .sort((a, b) => `${b.date}${b.kickoff ?? ""}`.localeCompare(`${a.date}${a.kickoff ?? ""}`));

  const leaguesMap = new Map([[code, league]]);

  return (
    <div className="space-y-8">
      <DatePicker selected={today} basePath={basePath} />
      <section>
        <h2 className="mb-4 text-xl font-bold tracking-tight text-foreground">
          {rolledOverDate ? `Next matchday: ${formatShortDate(rolledOverDate)}` : "Today"}
        </h2>
        {rolledOverDate ? (
          rolledOverMatches.length === 0 ? (
            <p className="text-sm text-muted">Nothing scheduled yet.</p>
          ) : (
            <DateMatchList matches={rolledOverMatches} leagues={leaguesMap} />
          )
        ) : todaySorted.length === 0 ? (
          <p className="text-sm text-muted">No matches today.</p>
        ) : (
          <DateMatchList matches={todaySorted} leagues={leaguesMap} />
        )}
      </section>
      {recentResults.length > 0 && (
        <section>
          <h2 className="mb-4 text-xl font-bold tracking-tight text-foreground">Recent results</h2>
          <DateMatchList matches={recentResults} leagues={leaguesMap} />
        </section>
      )}
    </div>
  );
}

async function PastSeasonView({
  code,
  standings,
}: {
  code: string;
  standings: Awaited<ReturnType<typeof api.standings>> | null;
}) {
  const results = standings
    ? await api.leagueFixtures(code, "finished", 100, standings.season).catch(() => [])
    : [];
  const sorted = [...results].sort((a, b) => `${b.date}`.localeCompare(`${a.date}`));

  return (
    <div className="space-y-6">
      {!standings && (
        <div className="glass border-dashed p-8 text-center">
          <p className="text-sm text-muted">No table available for this season on our free data sources.</p>
        </div>
      )}
      {sorted.length === 0 ? (
        <p className="text-sm text-muted">No finished matches on record for this season.</p>
      ) : (
        <ul className="divide-y divide-white/10 glass">
          {sorted.map((m) => (
            <li key={m.id}>
              <Link
                href={`/matches/${m.id}`}
                className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-white/[0.06]"
              >
                <span className="truncate text-foreground">
                  {m.home_team.name} {m.home_goals} &ndash; {m.away_goals} {m.away_team.name}
                </span>
                <span className="shrink-0 text-muted-2">{m.date}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
