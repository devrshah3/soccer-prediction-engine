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
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{code}</h1>
        <SeasonSelect code={code} season={standings.season} seasons={standings.available_seasons} />
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-[11px] uppercase tracking-wide text-muted-2">
            <tr>
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-3 py-3 font-medium">Team</th>
              <th className="px-2 py-3 text-right font-medium">P</th>
              <th className="px-2 py-3 text-right font-medium">W</th>
              <th className="px-2 py-3 text-right font-medium">D</th>
              <th className="px-2 py-3 text-right font-medium">L</th>
              <th className="px-2 py-3 text-right font-medium">GF</th>
              <th className="px-2 py-3 text-right font-medium">GA</th>
              <th className="px-2 py-3 text-right font-medium">GD</th>
              <th className="px-2 py-3 pr-4 text-right font-medium text-foreground">Pts</th>
              <th className="px-3 py-3 font-medium">Form</th>
            </tr>
          </thead>
          <tbody>
            {standings.table.map((row) => (
              <tr key={row.team_id} className="border-t border-border transition-colors hover:bg-surface-hover">
                <td className="px-4 py-2.5 tabular-nums text-muted-2">{row.position}</td>
                <td className="px-3 py-2.5">
                  <Link href={`/teams/${encodeURIComponent(row.team_id)}`} className="font-medium text-foreground hover:text-accent">
                    {row.team_name}
                  </Link>
                </td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.played}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.w}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.d}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.l}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.gf}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.ga}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-muted">{row.gd}</td>
                <td className="px-2 py-2.5 pr-4 text-right font-bold tabular-nums text-foreground">{row.pts}</td>
                <td className="px-3 py-2.5">
                  <FormDots form={row.form} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {trophyOdds && (
        <div>
          <h2 className="mb-1 text-lg font-semibold text-foreground">Trophy odds</h2>
          <p className="mb-4 text-xs text-muted-2">
            Monte Carlo simulation of the rest of the season ({trophyOdds.n_sims.toLocaleString()} runs over{" "}
            {trophyOdds.remaining_fixtures} remaining fixtures), model as of {trophyOdds.model_as_of}. Not a
            promise of accuracy.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {trophyOdds.teams.map((t) => (
              <Link
                key={t.team_id}
                href={`/teams/${encodeURIComponent(t.team_id)}`}
                className="rounded-xl border border-border bg-surface p-4 transition-colors hover:border-border-strong hover:bg-surface-hover"
              >
                <p className="mb-3 truncate text-sm font-medium text-foreground">{t.team_name}</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <OddStat label="Title" value={t.title_pct} />
                  <OddStat label="Top 4" value={t.top4_pct} />
                  <OddStat label="Releg." value={t.relegation_pct} tone="danger" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
      <p className="text-xs text-muted-2">
        Top scorers for this league (2024-25 season, most recent available on our free data
        tier) are on the <Link href="/awards" className="text-accent hover:underline">Awards</Link> page.
        A full assists/stat-leaders table isn&apos;t built yet.
      </p>
    </div>
  );
}

function OddStat({ label, value, tone }: { label: string; value: number; tone?: "danger" }) {
  return (
    <div>
      <p className={`text-sm font-bold tabular-nums ${tone === "danger" ? "text-danger" : "text-accent"}`}>
        {(value * 100).toFixed(1)}%
      </p>
      <p className="text-[10px] uppercase tracking-wide text-muted-2">{label}</p>
    </div>
  );
}
