import Link from "next/link";
import { notFound } from "next/navigation";
import { FormDots } from "@/components/FormDots";
import { SeasonSelect } from "@/components/SeasonSelect";
import { api, ApiError } from "@/lib/api";

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { code } = await params;
  const { season } = await searchParams;

  const standings = await api.standings(code, season).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  if (!standings) notFound();

  const trophyOdds =
    standings.season === standings.available_seasons[0]
      ? await api.trophyOdds(code, standings.season).catch((e) => {
          // 503 = not enough validated model history for this competition (e.g. Champions
          // League - see kickcast_api/predictions.py's explicit guard, a cross-league
          // rating is unvalidated future work) - a real, expected state, not a page error.
          if (e instanceof ApiError && e.status === 503) return null;
          throw e;
        })
      : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-zinc-50">{code}</h1>
        <SeasonSelect code={code} season={standings.season} seasons={standings.available_seasons} />
      </div>

      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-zinc-900 text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Team</th>
              <th className="px-2 py-2 text-center">P</th>
              <th className="px-2 py-2 text-center">W</th>
              <th className="px-2 py-2 text-center">D</th>
              <th className="px-2 py-2 text-center">L</th>
              <th className="px-2 py-2 text-center">GF</th>
              <th className="px-2 py-2 text-center">GA</th>
              <th className="px-2 py-2 text-center">GD</th>
              <th className="px-2 py-2 text-center font-bold">Pts</th>
              <th className="px-3 py-2">Form</th>
            </tr>
          </thead>
          <tbody>
            {standings.table.map((row) => (
              <tr key={row.team_id} className="border-t border-zinc-800 hover:bg-zinc-900/60">
                <td className="px-3 py-2 text-zinc-500">{row.position}</td>
                <td className="px-3 py-2">
                  <Link href={`/teams/${encodeURIComponent(row.team_id)}`} className="hover:text-emerald-400">
                    {row.team_name}
                  </Link>
                </td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.played}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.w}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.d}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.l}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.gf}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.ga}</td>
                <td className="px-2 py-2 text-center text-zinc-400">{row.gd}</td>
                <td className="px-2 py-2 text-center font-bold text-zinc-100">{row.pts}</td>
                <td className="px-3 py-2">
                  <FormDots form={row.form} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {trophyOdds && (
        <div>
          <h2 className="mb-1 text-lg font-semibold text-zinc-200">Trophy odds</h2>
          <p className="mb-3 text-xs text-zinc-500">
            Monte Carlo simulation of the rest of the season ({trophyOdds.n_sims.toLocaleString()} runs over{" "}
            {trophyOdds.remaining_fixtures} remaining fixtures), model as of {trophyOdds.model_as_of}. Not a
            promise of accuracy.
          </p>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="bg-zinc-900 text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-3 py-2">Team</th>
                  <th className="px-2 py-2 text-center">Title</th>
                  <th className="px-2 py-2 text-center">Top 4</th>
                  <th className="px-2 py-2 text-center">Relegation</th>
                </tr>
              </thead>
              <tbody>
                {trophyOdds.teams.map((t) => (
                  <tr key={t.team_id} className="border-t border-zinc-800">
                    <td className="px-3 py-2">
                      <Link href={`/teams/${encodeURIComponent(t.team_id)}`} className="hover:text-emerald-400">
                        {t.team_name}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-center text-zinc-300">{(t.title_pct * 100).toFixed(1)}%</td>
                    <td className="px-2 py-2 text-center text-zinc-300">{(t.top4_pct * 100).toFixed(1)}%</td>
                    <td className="px-2 py-2 text-center text-zinc-300">{(t.relegation_pct * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <p className="text-xs text-zinc-600">
        Top scorers for this league (2024-25 season, most recent available on our free data
        tier) are on the <Link href="/awards" className="text-emerald-500 hover:underline">Awards</Link> page.
        A full assists/stat-leaders table isn&apos;t built yet.
      </p>
    </div>
  );
}
