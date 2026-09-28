import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Match } from "@/lib/api";
import { MatchRow } from "./MatchRow";

function finished(overrides: Partial<Match>): Match {
  return {
    id: 1, league_code: "international", season: "2026-27", date: "2026-09-28", kickoff: "16:00", round: null,
    status: "finished", home_team: { id: "georgia", name: "Georgia" }, away_team: { id: "ukraine", name: "Ukraine" },
    home_goals: 0, away_goals: 0, neutral: false, source: "test", ...overrides,
  };
}

describe("a finished match never renders as 'score pending' when we hold its score", () => {
  it("status finished + stored score (even 0-0) shows the score and Full time", () => {
    const { container } = render(<MatchRow match={finished({ home_goals: 0, away_goals: 0 })} />);
    expect(screen.getByText("0 – 0")).toBeTruthy();
    expect(screen.getByText("Full time")).toBeTruthy();
    expect(container.textContent).not.toMatch(/pending|not available/i);
  });

  it("a stored score on a row still marked scheduled, long after kickoff, shows the score too", () => {
    const m = finished({ status: "scheduled", home_goals: 2, away_goals: 3, date: "2020-01-01" });
    const { container } = render(<MatchRow match={m} />);
    expect(screen.getByText("2 – 3")).toBeTruthy();
    expect(container.textContent).not.toMatch(/pending|not available/i);
  });

  it("with no data from any source it says 'Final score not available yet'", () => {
    render(<MatchRow match={finished({ status: "scheduled", home_goals: null, away_goals: null, date: "2020-01-01" })} />);
    expect(screen.getByText("Final score not available yet")).toBeTruthy();
    expect(screen.queryByText(/pending/i)).toBeNull();
  });
});
