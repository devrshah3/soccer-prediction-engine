import Link from "next/link";
import { Flag } from "@/components/Flag";
import { api, type League, type Match } from "@/lib/api";
import { formatShortDate } from "@/lib/time";

// Item 2's leagues hub: one glass tile per real competition in the DB (api.leagues() -
// never a hardcoded list, so this never shows a competition we don't actually have data
// for). Each tile's "Next: <date> - <n> matches" comes from a real /fixtures call, not an
// invented number. Item 3 adds the season selector and points-table sheet on top of this.
const WINDOW_DAYS = 30;
const WINDOW_LIMIT = 100;

export default async function LeaguesHubPage() {
  const leagues = await api.leagues();
  const codes = leagues.map((l) => l.code);
  const fixturesByLeague = await api
    .fixturesByLeagues(codes, "scheduled", WINDOW_LIMIT, WINDOW_DAYS)
    .catch(() => ({}) as Record<string, Match[]>);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Leagues</h1>
        <p className="mt-1 text-sm text-muted">Every competition we track, with real upcoming fixture counts.</p>
      </div>
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {leagues.map((league) => (
          <LeagueTile key={league.code} league={league} fixtures={fixturesByLeague[league.code] ?? []} />
        ))}
      </div>
    </div>
  );
}

function LeagueTile({ league, fixtures }: { league: League; fixtures: Match[] }) {
  const sorted = [...fixtures].sort((a, b) => `${a.date}${a.kickoff ?? ""}`.localeCompare(`${b.date}${b.kickoff ?? ""}`));
  const next = sorted[0];

  return (
    <Link
      href={`/leagues/${encodeURIComponent(league.code)}`}
      className="glass flex items-center gap-4 p-4 transition-all hover:-translate-y-0.5 hover:border-white/25"
    >
      <Flag country={league.country} className="h-9 w-12 shrink-0 rounded-md" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{league.name}</p>
        <p className="mt-0.5 text-xs text-muted-2">
          {next
            ? `Next: ${formatShortDate(next.date)} · ${sorted.length} match${sorted.length === 1 ? "" : "es"} in ${WINDOW_DAYS}d`
            : "No fixtures scheduled in the next 30 days"}
        </p>
      </div>
    </Link>
  );
}
