import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Match, PredictionSummary } from "@/lib/api";
import { MatchRow } from "./MatchRow";

const NOW = new Date("2026-09-28T15:00:00Z");

const prediction: PredictionSummary = {
  model_version: "test",
  as_of: "2026-09-28",
  computed_at: "2026-09-28T09:00:00Z",
  evidence: "A",
  probabilities: { home: 0.64, draw: 0.23, away: 0.13 },
};

function matchKickedOff(minutesAgo: number, overrides: Partial<Match> = {}): Match {
  const d = new Date(NOW.getTime() - minutesAgo * 60000);
  return {
    id: 1,
    league_code: "EPL",
    season: "2026",
    date: d.toISOString().slice(0, 10),
    kickoff: d.toISOString().slice(11, 16),
    round: null,
    status: "scheduled",
    home_team: { id: "a", name: "Alpha FC" },
    away_team: { id: "b", name: "Beta United" },
    home_goals: null,
    away_goals: null,
    neutral: false,
    source: "test",
    ...overrides,
  };
}

const bar = () => screen.queryByRole("img", { name: /Alpha FC 64%/ });

describe("MatchRow live/finished display", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("renders Live with the prediction bar still visible: kickoff 40 min ago, no finished flag", () => {
    render(<MatchRow match={matchKickedOff(40)} prediction={prediction} />);
    expect(screen.getByText("Live · kickoff 40 min ago")).toBeTruthy();
    expect(screen.getByText("No live score available")).toBeTruthy();
    expect(screen.getByText(/Pre-match prediction/)).toBeTruthy();
    expect(bar()).not.toBeNull();
    expect(screen.queryByText(/Full time/)).toBeNull();
  });

  it("shows a live score next to the still-visible bar when a provider gives one", () => {
    const live = { match_status: "2H", minute: 63, home_score: 1, away_score: 0, updated_at: "2026-09-28T14:55:00Z" };
    render(<MatchRow match={matchKickedOff(70, { live })} prediction={prediction} />);
    expect(screen.getByText("1 – 0")).toBeTruthy();
    expect(screen.getByText("Live · 63'")).toBeTruthy();
    expect(screen.queryByText("No live score available")).toBeNull();
    expect(bar()).not.toBeNull();
  });

  it("renders Finished with no bar when a source explicitly marks it finished", () => {
    const match = matchKickedOff(40, { status: "finished", home_goals: 2, away_goals: 1 });
    render(<MatchRow match={match} prediction={prediction} />);
    expect(screen.getByText("Full time")).toBeTruthy();
    expect(screen.getByText("2 – 1")).toBeTruthy();
    expect(bar()).toBeNull();
    expect(screen.queryByText(/Pre-match prediction/)).toBeNull();
  });

  it("renders Finished with no bar via the 150-minute fallback: kickoff 200 min ago, no flag", () => {
    render(<MatchRow match={matchKickedOff(200)} prediction={prediction} />);
    expect(screen.getByText("Final score not available yet")).toBeTruthy();
    expect(bar()).toBeNull();
  });
});
