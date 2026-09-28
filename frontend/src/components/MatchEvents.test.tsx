import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GoalEvent, Match } from "@/lib/api";
import { GoalList, GoalTimeline } from "./GoalList";
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

describe("finished match goals", () => {
  it("renders minute, scorer and marks a penalty and an own goal, under the right team", () => {
    render(<GoalList goals={goals} home={home} away={away} />);
    const lists = screen.getAllByRole("list");
    expect(within(lists[0]).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "34' Haaland",
      "67' Foden (pen)",
      "88' Maguire (og)",
    ]);
    expect(within(lists[1]).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["71' Fernandes"]);
  });

  it("the match-page timeline names the team and spells out own goals and penalties", () => {
    render(<GoalTimeline goals={goals} home={home} away={away} />);
    expect(screen.getByText(/Foden \(pen\.\)/)).toBeTruthy();
    expect(screen.getByText(/Maguire \(own goal\)/)).toBeTruthy();
    expect(screen.getAllByText(/Man City/)).toHaveLength(3);
  });

  it("a finished card with scorer data shows the score and the goal list, and no bar", () => {
    render(<MatchRow match={match({ status: "finished", home_goals: 3, away_goals: 1, goal_events: goals })} />);
    expect(screen.getByText("3 – 1")).toBeTruthy();
    expect(screen.getByText("67' Foden (pen)")).toBeTruthy();
  });

  it("a finished match with NO scorer data is score-only - no goal list and no 'not available' block", () => {
    const { container } = render(<MatchRow match={match({ status: "finished", home_goals: 2, away_goals: 0 })} />);
    expect(screen.getByText("2 – 0")).toBeTruthy();
    expect(screen.queryByLabelText("Goals")).toBeNull();
    expect(container.textContent).not.toMatch(/not available|aren't on record|unavailable/i);
  });
});
