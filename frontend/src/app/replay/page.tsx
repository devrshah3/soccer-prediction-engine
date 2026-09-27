import Link from "next/link";
import { api } from "@/lib/api";

export default async function ReplayListPage() {
  const { source, matches } = await api.replayMatches();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Historical Replay</h1>
        <p className="mt-2 text-sm text-muted">
          Real event data from {source}. This is a REPLAY of a past match, not a live feed.
        </p>
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {matches.map((m) => (
          <li key={m.id}>
            <Link
              href={`/replay/${m.id}`}
              className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-surface-hover"
            >
              <span className="truncate text-foreground">
                {m.home} <span className="font-semibold tabular-nums">{m.home_goals} &ndash; {m.away_goals}</span> {m.away}
              </span>
              <span className="shrink-0 text-muted-2">
                {m.competition} {m.season} &middot; {m.date}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
