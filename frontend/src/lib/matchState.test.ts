import { describe, expect, it } from "vitest";
import { matchState } from "./matchState";

describe("matchState", () => {
  it("is finished when status is finished", () => {
    expect(matchState({ status: "finished", date: "2026-01-01", kickoff: "12:00" })).toEqual({ kind: "finished" });
  });

  it("is upcoming before kickoff", () => {
    const future = new Date(Date.now() + 60 * 60 * 1000);
    const date = future.toISOString().slice(0, 10);
    const kickoff = future.toISOString().slice(11, 16);
    expect(matchState({ status: "scheduled", date, kickoff })).toEqual({ kind: "upcoming" });
  });

  it("is in_progress shortly after kickoff", () => {
    const past = new Date(Date.now() - 30 * 60 * 1000);
    const date = past.toISOString().slice(0, 10);
    const kickoff = past.toISOString().slice(11, 16);
    const state = matchState({ status: "scheduled", date, kickoff });
    expect(state.kind).toBe("in_progress");
  });

  it("is pending_result well after kickoff with no score", () => {
    const past = new Date(Date.now() - 200 * 60 * 1000);
    const date = past.toISOString().slice(0, 10);
    const kickoff = past.toISOString().slice(11, 16);
    expect(matchState({ status: "scheduled", date, kickoff })).toEqual({ kind: "pending_result" });
  });

  it("is upcoming when kickoff is unknown", () => {
    expect(matchState({ status: "scheduled", date: "2026-01-01", kickoff: null })).toEqual({ kind: "upcoming" });
  });
});
