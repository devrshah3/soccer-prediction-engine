import type { GoalEvent } from "@/lib/api";

// "34' Haaland", "67' Foden (pen)", "88' Smith (og)"
export function formatGoal(g: GoalEvent): string {
  const minute = g.minute != null ? `${g.minute}' ` : "";
  const mark = g.own_goal ? " (og)" : g.penalty ? " (pen)" : "";
  return `${minute}${g.scorer}${mark}`;
}

type Side = { id: string; name: string };

// Compact goal list for a match card: home goals under the home team, away under the away
// team, so the team never has to be spelled out. Renders NOTHING when there are no goals -
// callers never need a "not available" placeholder.
export function GoalList({ goals, home, away }: { goals: GoalEvent[] | undefined; home: Side; away: Side }) {
  if (!goals || goals.length === 0) return null;
  // If any goal's team couldn't be resolved, a two-column layout would misplace it - fall
  // back to one flat line, still in minute order.
  const resolvable = goals.every((g) => g.team_id === home.id || g.team_id === away.id);
  if (!resolvable) {
    return (
      <p className="mt-2 text-[11px] leading-snug text-muted" aria-label="Goals">
        {goals.map(formatGoal).join(", ")}
      </p>
    );
  }
  const column = (id: string) => goals.filter((g) => g.team_id === id);
  return (
    <div className="mt-2 grid grid-cols-2 gap-x-3 text-[11px] leading-snug text-muted" aria-label="Goals">
      <ul className="min-w-0 space-y-0.5">
        {column(home.id).map((g, i) => (
          <li key={i} className="truncate">{formatGoal(g)}</li>
        ))}
      </ul>
      <ul className="min-w-0 space-y-0.5 text-right">
        {column(away.id).map((g, i) => (
          <li key={i} className="truncate">{formatGoal(g)}</li>
        ))}
      </ul>
    </div>
  );
}

// Full goal list for the match page: minute, scorer, team, own goals/penalties marked.
export function GoalTimeline({ goals, home, away }: { goals: GoalEvent[] | undefined; home: Side; away: Side }) {
  if (!goals || goals.length === 0) return null;
  const teamName = (id: string | null) => (id === home.id ? home.name : id === away.id ? away.name : null);
  return (
    <ul className="mt-3 space-y-1.5" aria-label="Goals" aria-live="polite">
      {goals.map((g, i) => (
        <li key={`${g.minute}-${g.scorer}-${i}`} className="flex gap-3 text-sm">
          <span className="w-9 shrink-0 tabular-nums text-muted-2">{g.minute != null ? `${g.minute}'` : ""}</span>
          <span className="text-foreground">
            {g.scorer}
            {g.own_goal ? " (own goal)" : g.penalty ? " (pen.)" : ""}
            {teamName(g.team_id) && <> &mdash; {teamName(g.team_id)}</>}
          </span>
        </li>
      ))}
    </ul>
  );
}
