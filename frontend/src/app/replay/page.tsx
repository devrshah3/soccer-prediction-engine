import Link from "next/link";
import { api } from "@/lib/api";

export default async function ReplayListPage() {
  const { source, matches } = await api.replayMatches();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-zinc-50">Historical Replay</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Real event data from {source}. This is a REPLAY of a past match, not a live feed.
        </p>
      </div>
      <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
        {matches.map((m) => (
          <li key={m.id} className="px-4 py-3 text-sm">
            <Link href={`/replay/${m.id}`} className="hover:text-emerald-400">
              {m.date} &middot; {m.home} {m.home_goals} - {m.away_goals} {m.away} ({m.competition} {m.season})
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
