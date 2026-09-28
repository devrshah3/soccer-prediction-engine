import Link from "next/link";
import { nameForCode, slugForCode } from "@/lib/leagueSlugs";
import { ProbabilityBar } from "./ProbabilityBar";
import { TeamCrest } from "./TeamCrest";

type MatchData = {
  id: number;
  date: string;
  round: string | null;
  status: "scheduled" | "finished";
  home_team: { id: string; name: string };
  away_team: { id: string; name: string };
  home_goals: number | null;
  away_goals: number | null;
};

type Source =
  | { type: "kickcast_match"; data: MatchData }
  | {
      type: "kickcast_standings";
      data: { team_id: string; team_name: string; league_code: string; season: string; position: number; pts: number };
    }
  | {
      type: "kickcast_prediction";
      data: {
        match: MatchData | null;
        prediction: {
          home: string;
          away: string;
          evidence: string;
          probabilities: { home: number; draw: number; away: number };
        };
      };
    }
  | { type: "wikipedia"; title: string; url: string; license?: string }
  | { type: "youtube"; title?: string; url: string; channel?: string }
  | { type: "kickcast_tool"; [key: string]: unknown };

export function AssistantSourceCard({ source }: { source: Source }) {
  if (source.type === "kickcast_tool") return null;

  if (source.type === "kickcast_match") {
    const m = source.data;
    return (
      <Link
        href={`/matches/${m.id}`}
        className="block rounded-lg border border-border bg-surface-raised p-3 transition-colors hover:border-border-strong hover:bg-surface-hover"
      >
        {m.round && <p className="mb-1.5 text-[11px] text-muted-2">{m.round}</p>}
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
            <TeamCrest name={m.home_team.name} size="sm" /> {m.home_team.name}
          </span>
          <span className="shrink-0 font-semibold text-foreground">
            {m.status === "finished" ? `${m.home_goals} - ${m.away_goals}` : "vs"}
          </span>
          <span className="flex min-w-0 flex-1 items-center justify-end gap-1.5 truncate text-right">
            {m.away_team.name} <TeamCrest name={m.away_team.name} size="sm" />
          </span>
        </div>
        <p className="mt-1.5 text-[11px] text-muted-2">{m.date}</p>
      </Link>
    );
  }

  if (source.type === "kickcast_standings") {
    const s = source.data;
    return (
      <Link
        href={`/leagues/${slugForCode(s.league_code)}`}
        className="block rounded-lg border border-border bg-surface-raised p-3 text-sm transition-colors hover:border-border-strong hover:bg-surface-hover"
      >
        <span className="font-semibold text-accent-text">#{s.position}</span>{" "}
        <span className="font-medium text-foreground">{s.team_name}</span>
        <span className="text-muted-2"> &middot; {nameForCode(s.league_code)} &middot; {s.pts} pts</span>
      </Link>
    );
  }

  if (source.type === "kickcast_prediction") {
    const { match, prediction: p } = source.data;
    const homeLabel = match?.home_team.name ?? p.home;
    const awayLabel = match?.away_team.name ?? p.away;
    return (
      <div className="rounded-lg border border-border bg-surface-raised p-3">
        <p className="mb-2 text-xs font-medium text-muted">
          {homeLabel} vs {awayLabel}
        </p>
        <ProbabilityBar home={p.probabilities.home} draw={p.probabilities.draw} away={p.probabilities.away} homeLabel={homeLabel} awayLabel={awayLabel} />
      </div>
    );
  }

  if (source.type === "wikipedia") {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer"
        className="block truncate rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs text-muted transition-colors hover:border-border-strong hover:text-foreground"
      >
        Wikipedia &middot; {source.title}
      </a>
    );
  }

  if (source.type === "youtube") {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer"
        className="block truncate rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs text-muted transition-colors hover:border-border-strong hover:text-foreground"
      >
        YouTube &middot; {source.title ?? source.channel ?? "watch"}
      </a>
    );
  }

  return null;
}
