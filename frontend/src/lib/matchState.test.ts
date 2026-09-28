import { describe, expect, it } from "vitest";
import { matchState } from "./matchState";

const NOW = new Date("2026-09-28T15:00:00Z");
const ago = (min: number) => {
  const d = new Date(NOW.getTime() - min * 60000);
  return { date: d.toISOString().slice(0, 10), kickoff: d.toISOString().slice(11, 16) };
};

describe("matchState", () => {
  it("is finished (explicit) when status is finished", () => {
    expect(matchState({ status: "finished", ...ago(20), home_goals: 2, away_goals: 1 }, NOW)).toEqual({
      kind: "finished",
      explicit: true,
      score: { home: 2, away: 1 },
    });
  });

  it("is finished (explicit) when the provider reports a full-time code", () => {
    const live = { match_status: "FT", minute: 90, home_score: 1, away_score: 0, updated_at: "2026-09-28T14:55:00Z" };
    const s = matchState({ status: "scheduled", ...ago(110), live }, NOW);
    expect(s).toMatchObject({ kind: "finished", explicit: true, score: { home: 1, away: 0 } });
  });

  it("is scheduled before kickoff", () => {
    expect(matchState({ status: "scheduled", ...ago(-60) }, NOW)).toEqual({ kind: "scheduled" });
  });

  it("is scheduled when kickoff is unknown", () => {
    expect(matchState({ status: "scheduled", date: "2026-01-01", kickoff: null }, NOW)).toEqual({ kind: "scheduled" });
  });

  it("is live from elapsed time when there is no provider flag and no score", () => {
    const s = matchState({ status: "scheduled", ...ago(40) }, NOW);
    expect(s).toMatchObject({ kind: "live", providerLive: false, score: null });
  });

  it("is live with the provider's flag, minute and score when available", () => {
    const live = { match_status: "2H", minute: 63, home_score: 1, away_score: 0, updated_at: "2026-09-28T14:55:00Z" };
    const s = matchState({ status: "scheduled", ...ago(70), live }, NOW);
    expect(s).toMatchObject({ kind: "live", providerLive: true, providerMinute: 63, score: { home: 1, away: 0 } });
  });

  it("falls back to finished 150 minutes after kickoff with no finished flag", () => {
    expect(matchState({ status: "scheduled", ...ago(149) }, NOW).kind).toBe("live");
    expect(matchState({ status: "scheduled", ...ago(150) }, NOW)).toMatchObject({ kind: "finished", explicit: false });
  });
});
