import { LeagueChip } from "@/components/LeagueChip";
import { api } from "@/lib/api";

export default async function AwardsPage() {
  const [awards, leagues] = await Promise.all([api.awards(), api.leagues()]);
  const leagueInfo = Object.fromEntries(leagues.map((l) => [l.code, l]));
  const intl = awards.golden_boot.international_top_scorers_also_available;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-zinc-50">Awards</h1>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-zinc-200">Golden Boot</h2>
        <div className="space-y-6">
          {Object.entries(awards.golden_boot.by_league).map(([code, entry]) => {
            const league = leagueInfo[code];
            return (
              <div key={code}>
                <div className="mb-1 flex items-center gap-2">
                  {league && <LeagueChip name={league.name} country={league.country} />}
                </div>
                {entry.available ? (
                  <>
                    <p className="mb-2 text-xs text-zinc-500">
                      {entry.season} season · {entry.source}
                    </p>
                    <p className="mb-2 text-xs text-zinc-600">{entry.note}</p>
                    <ol className="space-y-1 text-sm text-zinc-300">
                      {entry.top_scorers.slice(0, 5).map((s, i) => (
                        <li key={`${s.player}-${s.team_id}`} className="flex justify-between border-b border-zinc-800 py-1">
                          <span>
                            {i + 1}. {s.player} <span className="text-zinc-500">({s.team_name})</span>
                          </span>
                          <span className="font-semibold">{s.goals}</span>
                        </li>
                      ))}
                    </ol>
                  </>
                ) : (
                  <p className="text-sm text-zinc-500">{entry.reason}</p>
                )}
              </div>
            );
          })}
        </div>

        {intl.international_top_scorers.length > 0 && (
          <div className="mt-6 border-t border-zinc-800 pt-4">
            <h3 className="mb-1 text-sm font-medium text-zinc-400">
              International top scorers (last {intl.lookback_days} days)
            </h3>
            <p className="mb-2 text-xs text-zinc-500">{intl.reason}</p>
            <ol className="space-y-1 text-sm text-zinc-300">
              {intl.international_top_scorers.map((s, i) => (
                <li key={`${s.player}-${s.team_id}`} className="flex justify-between border-b border-zinc-800 py-1">
                  <span>
                    {i + 1}. {s.player} <span className="text-zinc-500">({s.team_name})</span>
                  </span>
                  <span className="font-semibold">{s.goals}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-zinc-200">Ballon d&apos;Or / The Best</h2>
        <p className="text-sm text-zinc-500">{awards.ballon_dor.reason}</p>
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-zinc-200">Puskás Award</h2>
        <p className="text-sm text-zinc-500">{awards.puskas.reason}</p>
      </section>
    </div>
  );
}
