import Link from "next/link";
import { GoldenBootCard } from "@/components/GoldenBootCard";
import { SeasonSelect } from "@/components/SeasonSelect";
import { api } from "@/lib/api";

export default async function AwardsPage({ searchParams }: { searchParams: Promise<{ season?: string }> }) {
  const { season } = await searchParams;
  const [awards, leagues] = await Promise.all([api.awards(season), api.leagues()]);
  const leagueInfo = Object.fromEntries(leagues.map((l) => [l.code, l]));
  const intl = awards.golden_boot.international_top_scorers_also_available;

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Awards</h1>
        <div className="flex items-center gap-2">
          {awards.available_seasons.length > 1 && (
            <SeasonSelect basePath="/awards" season={awards.season} seasons={awards.available_seasons} />
          )}
          <Link href="/awards/method" className="glass-row px-3 py-1.5 text-xs text-muted transition-colors hover:text-foreground">
            Method
          </Link>
        </div>
      </div>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-foreground">Golden Boot</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {Object.entries(awards.golden_boot.by_league).map(([code, entry]) => (
            <GoldenBootCard key={code} code={code} league={leagueInfo[code]} entry={entry} />
          ))}
        </div>

        {intl && intl.international_top_scorers.length > 0 && (
          <div className="mt-4 glass p-4">
            <h3 className="mb-1 text-sm font-medium text-foreground">
              International top scorers (last {intl.lookback_days} days)
            </h3>
            <p className="mb-3 text-xs text-muted-2">{intl.reason}</p>
            <ol className="space-y-1.5">
              {intl.international_top_scorers.map((s, i) => (
                <li key={`${s.player}-${s.team_id}`} className="flex items-center justify-between gap-3 glass-row px-3 py-2">
                  <span className="flex min-w-0 items-center gap-2.5 text-sm text-foreground">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/10 text-[10px] font-bold text-muted-2">
                      {i + 1}
                    </span>
                    <span className="truncate">
                      {s.player} <span className="text-muted-2">({s.team_name})</span>
                    </span>
                  </span>
                  <span className="shrink-0 font-bold tabular-nums text-accent">{s.goals}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="glass p-4">
          <h2 className="mb-1 text-sm font-semibold text-foreground">Ballon d&apos;Or / The Best</h2>
          <p className="text-sm text-muted">{awards.ballon_dor.reason}</p>
        </div>
        <div className="glass p-4">
          <h2 className="mb-1 text-sm font-semibold text-foreground">Puskás Award</h2>
          <p className="text-sm text-muted">{awards.puskas.reason}</p>
        </div>
      </section>
    </div>
  );
}
