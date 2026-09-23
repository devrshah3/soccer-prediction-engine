import Link from "next/link";
import type { League, Match, Prediction } from "@/lib/api";
import { KickoffTime } from "./KickoffTime";
import { LeagueChip } from "./LeagueChip";
import { ProbabilityBar } from "./ProbabilityBar";

export function MatchRow({
  match,
  league,
  prediction,
}: {
  match: Match;
  league?: League;
  prediction?: Prediction | null;
}) {
  const finished = match.status === "finished";
  return (
    <Link
      href={`/matches/${match.id}`}
      className="block rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-emerald-700"
    >
      <div className="mb-2 flex items-center justify-between">
        {league ? <LeagueChip name={league.name} country={league.country} /> : <span />}
        <span className="text-xs text-zinc-500">
          {match.round ?? ""} &middot; <KickoffTime date={match.date} kickoff={match.kickoff} />
        </span>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="flex-1 truncate text-sm font-medium text-zinc-100">{match.home_team.name}</span>
        {finished ? (
          <span className="shrink-0 rounded bg-zinc-800 px-2 py-0.5 text-sm font-bold text-zinc-100">
            {match.home_goals} - {match.away_goals}
          </span>
        ) : (
          <span className="shrink-0 text-xs text-zinc-500">vs</span>
        )}
        <span className="flex-1 truncate text-right text-sm font-medium text-zinc-100">{match.away_team.name}</span>
      </div>
      {!finished && prediction && (
        <div className="mt-3">
          <ProbabilityBar
            home={prediction.probabilities.home}
            draw={prediction.probabilities.draw}
            away={prediction.probabilities.away}
            homeLabel={match.home_team.name}
            awayLabel={match.away_team.name}
          />
          <p className="mt-1 text-[11px] text-zinc-500">
            as of {prediction.as_of} &middot; evidence {prediction.evidence} &middot; {prediction.model_version}
          </p>
        </div>
      )}
      {!finished && !prediction && (
        <p className="mt-2 text-xs text-zinc-500">prediction not available yet</p>
      )}
    </Link>
  );
}
