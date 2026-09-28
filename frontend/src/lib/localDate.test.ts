import { describe, expect, it } from "vitest";
import { localCalendarDate } from "./localDate";

describe("localCalendarDate", () => {
  it("stays on the same day when the local offset doesn't cross midnight", () => {
    // 19:00 UTC, London (UTC+0 in this test) - same calendar day either way.
    const match = { date: "2026-08-21", kickoff: "19:00" };
    expect(localCalendarDate(match, 0)).toBe("2026-08-21");
  });

  it("the day-boundary case: a 9pm US Eastern kickoff is stored as the next UTC day", () => {
    // 21:00 Eastern (UTC-4 in summer) = 01:00 UTC the next calendar day - exactly what
    // the brief calls out. Stored match.date is already the UTC day (2026-08-22).
    const match = { date: "2026-08-22", kickoff: "01:00" };
    // A viewer physically in US Eastern (offset -240 minutes) should see this as 2026-08-21.
    expect(localCalendarDate(match, -240)).toBe("2026-08-21");
    // A European viewer (offset +60) sees the same calendar day as the stored UTC date.
    expect(localCalendarDate(match, 60)).toBe("2026-08-22");
  });

  it("falls back to the stored date when kickoff time is unknown", () => {
    expect(localCalendarDate({ date: "2026-08-21", kickoff: null }, -240)).toBe("2026-08-21");
  });
});
