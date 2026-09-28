import { afterEach, describe, expect, it, vi } from "vitest";
import { tzOffsetMinutesEast } from "./replayDate";

describe("tzOffsetMinutesEast", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is positive east of UTC and negative west of it (the negation of getTimezoneOffset)", () => {
    const eastern = new Date("2026-09-28T02:00:00Z");
    vi.spyOn(eastern, "getTimezoneOffset").mockReturnValue(240); // US Eastern (UTC-4)
    expect(tzOffsetMinutesEast(eastern)).toBe(-240);

    const tokyo = new Date("2026-09-28T02:00:00Z");
    vi.spyOn(tokyo, "getTimezoneOffset").mockReturnValue(-540); // UTC+9
    expect(tzOffsetMinutesEast(tokyo)).toBe(540);
  });

  it("is a plain 0 (not -0) for UTC", () => {
    const utc = new Date("2026-09-28T02:00:00Z");
    vi.spyOn(utc, "getTimezoneOffset").mockReturnValue(0);
    expect(Object.is(tzOffsetMinutesEast(utc), 0)).toBe(true);
  });
});
