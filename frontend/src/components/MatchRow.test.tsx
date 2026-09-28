import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { League, Match, PredictionSummary } from "@/lib/api";
import { MatchRow } from "./MatchRow";

const match: Match = {
  id: 1,
  league_code: "en.1",
  season: "2026-27",
  date: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  kickoff: "15:00",
  round: "Matchday 6",
  status: "scheduled",
  home_team: { id: "arsenal", name: "Arsenal" },
  away_team: { id: "leeds united", name: "Leeds" },
  home_goals: null,
  away_goals: null,
  neutral: false,
  source: "synthetic",
};

const league: League = { code: "en.1", name: "Premier League", country: "England", kind: "domestic_league" };

const prediction: PredictionSummary = {
  model_version: "dixon-coles-v1",
  as_of: "2026-09-20",
  computed_at: new Date().toISOString(),
  evidence: "A",
  probabilities: { home: 0.5, draw: 0.3, away: 0.2 },
};

// D.11 / item 13: a normal card must NOT show model/evidence/computed-at text directly -
// that provenance only appears inside the (i) popover, on demand.
describe("MatchRow provenance disclosure", () => {
  it("does not render provenance text on a normal card", () => {
    render(<MatchRow match={match} league={league} prediction={prediction} />);
    expect(screen.queryByText(/dixon-coles-v1/)).toBeNull();
    expect(screen.queryByText(/evidence tier/i)).toBeNull();
    expect(screen.queryByText(/data cutoff/i)).toBeNull();
  });

  it("reveals provenance details when the (i) popover is opened", () => {
    render(<MatchRow match={match} league={league} prediction={prediction} />);
    const infoButton = screen.getByLabelText(/prediction details/i);
    expect(screen.queryByText(/dixon-coles-v1/)).toBeNull();
    fireEvent.click(infoButton);
    expect(screen.getByText(/dixon-coles-v1/)).toBeTruthy();
    expect(screen.getByText(/evidence tier/i)).toBeTruthy();
    expect(screen.getByText(/data cutoff/i)).toBeTruthy();
  });

  it("shows no staleness tag for a freshly-computed prediction", () => {
    render(<MatchRow match={match} league={league} prediction={prediction} />);
    expect(screen.queryByText(/may be outdated/i)).toBeNull();
  });

  it("shows the staleness tag for a genuinely stale prediction on a near-term match", () => {
    const stale: PredictionSummary = { ...prediction, computed_at: new Date(Date.now() - 72 * 60 * 60 * 1000).toISOString() };
    render(<MatchRow match={match} league={league} prediction={stale} />);
    expect(screen.getByText(/may be outdated/i)).toBeTruthy();
  });
});
