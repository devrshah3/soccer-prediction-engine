import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GoalEvent, Match } from "@/lib/api";
import { MatchRow } from "./MatchRow";

const home = { id: "city", name: "Man City" };
const away = { id: "united", name: "Man United" };
const NOW = new Date("2026-09-28T15:00:00Z");

const goals: GoalEvent[] = [
  { team_id: "city", scorer: "Haaland", minute: 34, own_goal: false, penalty: false },
  { team_id: "city", scorer: "Foden", minute: 67, own_goal: false, penalty: true },
  { team_id: "city", scorer: "Maguire", minute: 88, own_goal: true, penalty: false }, // credited to City
  { team_id: "united", scorer: "Fernandes", minute: 71, own_goal: false, penalty: false },
];

function match(overrides: Partial<Match>): Match {
  const kickoff = new Date(NOW.getTime() - 40 * 60000);
  return {
    id: 1, league_code: "EPL", season: "2026", date: kickoff.toISOString().slice(0, 10), kickoff: kickoff.toISOString().slice(11, 16),
    round: null, status: "scheduled", home_team: home, away_team: away, home_goals: null, away_goals: null,
    neutral: false, source: "test", ...overrides,
  };
}

describe("live match goals", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  const live = (n: number) => ({
    match_status: "2H", minute: 50, home_score: n, away_score: 0, updated_at: new Date(NOW.getTime() - 3 * 60000).toISOString(),
  });

  it("the goal list grows when a new event is polled in, and the score updates with it", () => {
    const first: GoalEvent[] = [goals[0]];
    const { rerender } = render(<MatchRow match={match({ live: live(1), goal_events: first })} />);
    expect(screen.getByText("1 – 0")).toBeTruthy();
    expect(screen.getByText("Live · 50'")).toBeTruthy();
    expect(within(screen.getByLabelText("Goals")).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("score updated 3m ago")).toBeTruthy();

    // next poll: a second goal has been scored
    rerender(<MatchRow match={match({ live: live(2), goal_events: [goals[0], goals[1]] })} />);
    expect(screen.getByText("2 – 0")).toBeTruthy();
    expect(within(screen.getByLabelText("Goals")).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("67' Foden (pen)")).toBeTruthy();
  });

  it("keeps the pre-match bar while showing the live score", () => {
    render(
      <MatchRow
        match={match({ live: live(1), goal_events: [goals[0]] })}
        prediction={{ model_version: "t", as_of: "2026-09-28", computed_at: null, evidence: "A", probabilities: { home: 0.6, draw: 0.25, away: 0.15 } }}
      />
    );
    expect(screen.getByRole("img", { name: /Man City 60%/ })).toBeTruthy();
  });

  it("with no live-events source: elapsed time, no score, no goal list", () => {
    render(<MatchRow match={match({})} />);
    expect(screen.getByText("Live · kickoff 40 min ago")).toBeTruthy();
    expect(screen.getByText("No live score available")).toBeTruthy();
    expect(screen.queryByLabelText("Goals")).toBeNull();
  });
});
