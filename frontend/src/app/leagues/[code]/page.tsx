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
      <p className="text-xs text-zinc-600">
        Stat leaders (goals/assists) aren&apos;t shown yet - we don&apos;t have a verified free source of
        per-player domestic stats. See MORNING_REPORT.md.
      </p>
    </div>
  );
}
