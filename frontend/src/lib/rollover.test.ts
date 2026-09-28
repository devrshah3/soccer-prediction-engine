import { describe, expect, it } from "vitest";
import { isTodaySettled } from "./rollover";

const DAY = "2026-09-27";

describe("isTodaySettled", () => {
  it("is not settled before the first kickoff", () => {
    const now = new Date(`${DAY}T10:00:00Z`);
    const matches = [{ status: "scheduled" as const, date: DAY, kickoff: "16:00" }];
    expect(isTodaySettled(matches, now)).toBe(false);
  });

  it("is not settled mid-day while a match is in progress with no score yet", () => {
    const now = new Date(`${DAY}T16:30:00Z`); // 30 min after a 16:00 kickoff
    const matches = [{ status: "scheduled" as const, date: DAY, kickoff: "16:00" }];
    expect(isTodaySettled(matches, now)).toBe(false);
  });

  it("is settled after the last match finishes", () => {
    const now = new Date(`${DAY}T22:00:00Z`);
    const matches = [
      { status: "finished" as const, date: DAY, kickoff: "12:00" },
      { status: "finished" as const, date: DAY, kickoff: "16:00" },
    ];
    expect(isTodaySettled(matches, now)).toBe(true);
  });

  it("is settled once every match is past the pending-result window even with no score", () => {
    const now = new Date(`${DAY}T20:00:00Z`); // 8h after a 12:00 kickoff - well past 135 min
    const matches = [{ status: "scheduled" as const, date: DAY, kickoff: "12:00" }];
    expect(isTodaySettled(matches, now)).toBe(true);
  });

  it("is not settled if even one of several matches is still in progress", () => {
    const now = new Date(`${DAY}T16:10:00Z`);
    const matches = [
      { status: "finished" as const, date: DAY, kickoff: "12:00" },
      { status: "scheduled" as const, date: DAY, kickoff: "16:00" }, // just kicked off
    ];
    expect(isTodaySettled(matches, now)).toBe(false);
  });

  it("is settled (nothing to roll away from) on a day with no matches", () => {
    expect(isTodaySettled([])).toBe(true);
  });
});
