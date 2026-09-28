import { describe, expect, it } from "vitest";
import { isPredictionStale } from "./predictionFreshness";

describe("isPredictionStale", () => {
  it("is not stale when computed recently for a near-term match", () => {
    const now = new Date("2026-09-28T12:00:00Z");
    const computedAt = new Date("2026-09-28T00:00:00Z").toISOString(); // 12h ago
    expect(isPredictionStale(computedAt, "2026-09-30", now)).toBe(false);
  });

  it("is stale when computed over 48h ago for a match within 7 days", () => {
    const now = new Date("2026-09-28T12:00:00Z");
    const computedAt = new Date("2026-09-25T00:00:00Z").toISOString(); // ~87h ago
    expect(isPredictionStale(computedAt, "2026-09-30", now)).toBe(true);
  });

  it("is not stale for a long-range match even if computed long ago", () => {
    const now = new Date("2026-09-28T12:00:00Z");
    const computedAt = new Date("2026-09-01T00:00:00Z").toISOString();
    expect(isPredictionStale(computedAt, "2026-12-25", now)).toBe(false);
  });

  it("is not stale when there is no computed_at to judge from", () => {
    expect(isPredictionStale(null, "2026-09-30")).toBe(false);
  });
});
