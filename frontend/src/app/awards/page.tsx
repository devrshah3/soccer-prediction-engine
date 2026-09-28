import { LeagueChip } from "@/components/LeagueChip";
import { api } from "@/lib/api";

export default async function AwardsPage() {
  const [awards, leagues] = await Promise.all([api.awards(), api.leagues()]);
  const leagueInfo = Object.fromEntries(leagues.map((l) => [l.code, l]));
  const intl = awards.golden_boot.international_top_scorers_also_available;

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Awards</h1>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-foreground">Golden Boot</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {Object.entries(awards.golden_boot.by_league).map(([code, entry]) => {
            const league = leagueInfo[code];
            return (
              <div key={code} className="glass p-4">
                <div className="mb-3 flex items-center gap-2">
                  {league && <LeagueChip name={league.name} country={league.country} />}
                </div>
                {entry.available ? (
                  <>
                    <p className="mb-1 text-xs text-muted-2">
                      {entry.season} season &middot; {entry.source}
                    </p>
                    <p className="mb-3 text-xs text-muted-2">{entry.note}</p>
                    <ol className="space-y-1.5">
                      {entry.top_scorers.slice(0, 5).map((s, i) => (
                        <li key={`${s.player}-${s.team_id}`} className="flex items-center justify-between gap-3 rounded-lg bg-surface-raised px-3 py-2">
                          <span className="flex min-w-0 items-center gap-2.5 text-sm text-foreground">
                            <RankBadge rank={i + 1} />
                            <span className="truncate">
                              {s.player} <span className="text-muted-2">({s.team_name})</span>
                            </span>
                          </span>
                          <span className="shrink-0 font-bold tabular-nums text-accent">{s.goals}</span>
                        </li>
                      ))}
                    </ol>
                  </>
                ) : (
                  <p className="text-sm text-muted">{entry.reason}</p>
                )}
              </div>
            );
          })}
        </div>

        {intl.international_top_scorers.length > 0 && (
          <div className="mt-4 glass p-4">
            <h3 className="mb-1 text-sm font-medium text-foreground">
              International top scorers (last {intl.lookback_days} days)
            </h3>
            <p className="mb-3 text-xs text-muted-2">{intl.reason}</p>
            <ol className="space-y-1.5">
              {intl.international_top_scorers.map((s, i) => (
                <li key={`${s.player}-${s.team_id}`} className="flex items-center justify-between gap-3 rounded-lg bg-surface-raised px-3 py-2">
                  <span className="flex min-w-0 items-center gap-2.5 text-sm text-foreground">
                    <RankBadge rank={i + 1} />
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

function RankBadge({ rank }: { rank: number }) {
  const isTop3 = rank <= 3;
  return (
    <span
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
        isTop3 ? "bg-accent-soft text-accent" : "bg-surface text-muted-2"
      }`}
    >
      {rank}
    </span>
  );
}
