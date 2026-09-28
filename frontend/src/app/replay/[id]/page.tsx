import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";

function describeEvent(e: { type: string; minute: number; team: string | null; player?: string | null; detail?: string | null; player_off?: string | null; player_on?: string | null; card?: string }): string {
  switch (e.type) {
    case "goal":
      return `Goal! ${e.player} (${e.team})${e.detail && e.detail !== "Open Play" ? ` - ${e.detail}` : ""}`;
    case "own_goal":
      return `Own goal, ${e.player} (${e.team})`;
    case "card":
      return `${e.card}: ${e.player} (${e.team})`;
    case "substitution":
      return `Substitution (${e.team}): ${e.player_on} on for ${e.player_off}`;
    default:
      return e.type;
  }
}

export default async function ReplayMatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const match = await api.replayMatch(id).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  if (!match) notFound();

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
        Historical Replay &mdash; {match.competition} {match.season}, {match.date}. This already happened; it is
        not a live match.
      </div>
      <h1 className="text-xl font-semibold tracking-tight text-foreground">
        {match.home} <span className="tabular-nums">{match.home_goals} &ndash; {match.away_goals}</span> {match.away}
      </h1>
      <ul className="space-y-1 glass p-2">
        {match.timeline.map((e, i) => (
          <li key={i} className="flex gap-3 rounded-lg px-3 py-2 text-sm transition-colors hover:bg-surface-hover">
            <span className="w-9 shrink-0 tabular-nums text-muted-2">{e.minute}&apos;</span>
            <span className="text-foreground">{describeEvent(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
