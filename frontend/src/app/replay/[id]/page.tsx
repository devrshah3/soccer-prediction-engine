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
      <div className="rounded-md border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
        Historical Replay - {match.competition} {match.season}, {match.date}. This already happened; it is
        not a live match.
      </div>
      <h1 className="text-xl font-semibold text-zinc-50">
        {match.home} {match.home_goals} - {match.away_goals} {match.away}
      </h1>
      <ul className="space-y-2">
        {match.timeline.map((e, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="w-10 shrink-0 text-zinc-500">{e.minute}&apos;</span>
            <span className="text-zinc-200">{describeEvent(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
