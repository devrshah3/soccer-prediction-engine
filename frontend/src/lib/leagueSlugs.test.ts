import { describe, expect, it } from "vitest";
import { CODE_TO_SLUG, nameForCode, slugForCode } from "./leagueSlugs";

// Item 4: every real competition code in the DB must resolve to a human display name and
// a clean slug, never fall through to showing the raw code itself.
describe("leagueSlugs", () => {
  it("gives every mapped code a real name, not the code itself", () => {
    for (const code of Object.keys(CODE_TO_SLUG)) {
      expect(nameForCode(code)).not.toBe(code);
    }
  });

  it("resolves the known competitions to their real names", () => {
    expect(nameForCode("en.1")).toBe("Premier League");
    expect(nameForCode("es.1")).toBe("La Liga");
    expect(nameForCode("it.1")).toBe("Serie A");
    expect(nameForCode("de.1")).toBe("Bundesliga");
    expect(nameForCode("fr.1")).toBe("Ligue 1");
    expect(nameForCode("CL")).toBe("UEFA Champions League");
  });

  it("gives every mapped code a clean, non-dotted slug", () => {
    for (const slug of Object.values(CODE_TO_SLUG)) {
      expect(slug).not.toMatch(/\./);
    }
  });

  it("falls back to the raw code only for a genuinely unmapped one (never crashes)", () => {
    expect(slugForCode("zz.9")).toBe("zz.9");
  });
});
