import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReplayMatch } from "@/lib/api";
import { ReplayMatchCard } from "./ReplayMatchCard";

const NOTE = "Detailed events aren't available for this match on our free data sources.";

const base: ReplayMatch = {
  id: 1,
  league_code: "international",
  league_name: "International",
  league_country: null,
  round: "Group A",
  date: "2026-09-27",
  kickoff: "16:00",
  status: "finished",
  home_team: { id: "serbia", name: "Serbia" },
  away_team: { id: "netherlands", name: "Netherlands" },
  home_goals: 1,
  away_goals: 2,
  has_result: true,
  events: [
    { minute: 10, player: "A Striker", team_id: "serbia", team_name: "Serbia", own_goal: false, penalty: false },
    { minute: 55, player: "B Winger", team_id: "netherlands", team_name: "Netherlands", own_goal: false, penalty: true },
    { minute: 88, player: "C Defender", team_id: "netherlands", team_name: "Netherlands", own_goal: true, penalty: false },
  ],
  events_status: "complete",
  prediction: null,
  prediction_result: {
    predicted: "home",
    predicted_probability: 0.5,
    actual: "away",
    actual_probability: 0.25,
    correct: false,
  },
  recap: { text: "Serbia 1-2 Netherlands.", mode: "template", label: "Recap written from verified match data" },
};

describe("ReplayMatchCard", () => {
  it("shows the score, every recorded goal with penalty/own-goal tags, and the recap label", () => {
    render(<ReplayMatchCard match={base} noEventsNote={NOTE} />);
    expect(screen.getByText(/1 . 2/)).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Penalty")).toBeTruthy();
    expect(screen.getByText("Own goal")).toBeTruthy();
    expect(screen.getByText("Recap written from verified match data")).toBeTruthy();
    expect(screen.queryByText(NOTE)).toBeNull();
  });

  it("compares the pre-match prediction with the result", () => {
    render(<ReplayMatchCard match={base} noEventsNote={NOTE} />);
    expect(screen.getByText("Prediction missed")).toBeTruthy();
    expect(screen.getByText(/favoured Serbia win \(50%\), got Netherlands win \(25%\)/)).toBeTruthy();
  });

  it("says plainly when no events are available and never invents a timeline", () => {
    render(
      <ReplayMatchCard
        match={{ ...base, events: [], events_status: "none", prediction_result: null }}
        noEventsNote={NOTE}
      />
    );
    expect(screen.getByText(NOTE)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Match events" })).toBeNull();
    expect(screen.getByText("No pre-match prediction on record for this match.")).toBeTruthy();
  });

  it("shows no score and a pending note when the result hasn't arrived", () => {
    render(
      <ReplayMatchCard
        match={{
          ...base,
          has_result: false,
          home_goals: null,
          away_goals: null,
          events: [],
          events_status: null,
          prediction_result: null,
        }}
        noEventsNote={NOTE}
      />
    );
    expect(screen.getByText(/Result not available yet/)).toBeTruthy();
    expect(screen.queryByText(NOTE)).toBeNull();
  });
});
