import { InfoPopover } from "./glass/InfoPopover";
import { LeagueChip } from "./LeagueChip";
import type { GoldenBootLeague, League } from "@/lib/api";

// Item 5: one card per competition. Only the essentials show by default - a short
// "Current season"/"Final" tag plus the leaderboard; source/season/method text lives
// behind the (i) popover, not as a long grey disclaimer line under every card.
export function GoldenBootCard({ league, code, entry }: { league?: League; code: string; entry: GoldenBootLeague }) {
  return (
    <div className="glass min-w-0 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        {league ? <LeagueChip name={league.name} country={league.country} /> : <span className="text-sm text-muted">{code}</span>}
        {entry.available && (
          <InfoPopover
            label="Source details"
            title="Where this comes from"
            lines={
              entry.tag === "Final"
                ? [`Season: ${entry.season}`, `Source: ${entry.source}`]
                : [`Season: ${entry.season}`, `Source: ${entry.source}`, entry.method]
            }
          />
        )}
      </div>

      {!entry.available ? (
        <p className="text-sm text-muted">{entry.reason}</p>
      ) : entry.tag === "Final" ? (
        <>
          <Tag tone="neutral">Final &middot; {entry.season}</Tag>
          <ol className="mt-3 space-y-1.5">
            {entry.top_scorers.slice(0, 5).map((s, i) => (
              <li key={`${s.player}-${s.team_id}`} className="flex items-center justify-between gap-3 glass-row px-3 py-2">
                <span className="flex min-w-0 items-center gap-2.5 text-sm text-foreground">
                  <RankBadge rank={i + 1} />
                  <span className="truncate">
                    {s.player} <span className="text-muted-2">({s.team_name})</span>
                  </span>
                </span>
                <span className="shrink-0 font-bold tabular-nums text-accent-text">{s.goals}</span>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <>
          <Tag tone="accent">Current season &middot; {entry.season}</Tag>
          <ol className="mt-3 space-y-1.5">
            {entry.scorers.slice(0, 5).map((s, i) => (
              <li key={`${s.player}-${s.team_id}`} className="glass-row min-w-0 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2.5 text-sm text-foreground">
                    <RankBadge rank={i + 1} />
                    <span className="truncate">
                      {s.player} <span className="text-muted-2">({s.team_name})</span>
                    </span>
                  </span>
                  <span className="shrink-0 font-bold tabular-nums text-accent-text">{s.goals_so_far}</span>
                </div>
                <p className="mt-1 pl-7 text-[11px] text-muted-2">
                  Projected {s.projected_final} ({s.projected_range[0]}&ndash;{s.projected_range[1]}) &middot;{" "}
                  {Math.round(s.top_scorer_chance * 100)}% to finish top scorer
                </p>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function Tag({ tone, children }: { tone: "accent" | "neutral"; children: React.ReactNode }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        tone === "accent" ? "bg-accent-soft text-accent-text" : "glass-row text-muted-2"
      }`}
    >
      {children}
    </span>
  );
}

function RankBadge({ rank }: { rank: number }) {
  const isTop3 = rank <= 3;
  return (
    <span
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
        isTop3 ? "bg-accent-soft text-accent-text" : "bg-white/10 text-muted-2"
      }`}
    >
      {rank}
    </span>
  );
}
