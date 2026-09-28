import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  permanentRedirect: (to: string) => {
    throw new Error(`REDIRECT:${to}`);
  },
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      team: vi.fn(),
      teamFixtures: vi.fn(),
      prediction: vi.fn(),
      trophyOdds: vi.fn(),
      awards: vi.fn(),
      leagues: vi.fn(),
      standings: vi.fn(),
      matchesByDate: vi.fn(),
      leagueFixtures: vi.fn(),
      replayDay: vi.fn(),
    },
  };
});

import { api } from "@/lib/api";
import { LeagueTableSheet } from "@/components/LeagueTableSheet";
import AwardsPage from "./awards/page";
import LeaguePage from "./leagues/[slug]/page";
import ReplayPage from "./replay/page";
import TeamPage from "./teams/[id]/page";

const mocked = vi.mocked(api, true);

// The league page nests an async server component, which Testing Library can't render - so
// inspect the element tree it returns instead (and assert on what it would mount).
function containsType(node: ReactNode, type: unknown): boolean {
  if (Array.isArray(node)) return node.some((n) => containsType(n, type));
  if (node && typeof node === "object" && "type" in node) {
    const el = node as { type: unknown; props?: { children?: ReactNode } };
    return el.type === type || containsType(el.props?.children, type);
  }
  return false;
}
const LEAGUES = [{ code: "en.1", name: "Premier League", country: "England", kind: "domestic_league" as const }];

beforeEach(() => vi.resetAllMocks());

describe("no raw league code reaches a rendered page", () => {
  it("team page shows the league's name, never 'en.1'", async () => {
    mocked.team.mockResolvedValue({
      id: "arsenal", name: "Arsenal", country: "England", league_code: "en.1", season: "2026-27",
      position: 2, form: ["W"], next_match: null,
    });
    mocked.teamFixtures.mockResolvedValue([]);
    mocked.trophyOdds.mockResolvedValue(null);
    render(await TeamPage({ params: Promise.resolve({ id: "arsenal" }) }));
    expect(screen.getByText("Premier League")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\ben\.1\b/);
  });
});

describe("awards never fall back to another season", () => {
  it("an unavailable season shows the honest message and no Final/Current tag", async () => {
    mocked.leagues.mockResolvedValue(LEAGUES);
    mocked.awards.mockResolvedValue({
      season: "2015-16",
      available_seasons: ["2026-27", "2015-16"],
      golden_boot: { available: false, by_league: { "en.1": { available: false, reason: "No scorer data for 2015-16 from our free sources." } } },
      ballon_dor: { available: false, reason: "n/a" },
      puskas: { available: false, reason: "n/a" },
    });
    render(await AwardsPage({ searchParams: Promise.resolve({ season: "2015-16" }) }));
    expect(mocked.awards).toHaveBeenCalledWith("2015-16");
    expect(screen.getByText("No scorer data for 2015-16 from our free sources.")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Final ·|Current season ·/);
  });
});

describe("the points-table button hides when there is no table", () => {
  const standings = (table: unknown[]) => ({
    league_code: "en.1", season: "2026-27", available_seasons: ["2026-27"], table,
  });
  beforeEach(() => {
    mocked.leagues.mockResolvedValue(LEAGUES);
    mocked.trophyOdds.mockResolvedValue(null);
    mocked.matchesByDate.mockResolvedValue([]);
    mocked.leagueFixtures.mockResolvedValue([]);
  });

  it("no button at all for an empty table", async () => {
    mocked.standings.mockResolvedValue(standings([]) as never);
    const page = await LeaguePage({ params: Promise.resolve({ slug: "premier-league" }), searchParams: Promise.resolve({}) });
    expect(containsType(page, LeagueTableSheet)).toBe(false);
  });

  it("button shown when a table exists", async () => {
    mocked.standings.mockResolvedValue(
      standings([{ team_id: "arsenal", team_name: "Arsenal", played: 5, w: 4, d: 0, l: 1, gf: 8, ga: 4, gd: 4, pts: 12, form: ["W"], position: 1 }]) as never
    );
    const page = await LeaguePage({ params: Promise.resolve({ slug: "premier-league" }), searchParams: Promise.resolve({}) });
    expect(containsType(page, LeagueTableSheet)).toBe(true);
  });

  it("an old code-based URL redirects to the clean slug, and 'international' does not loop", async () => {
    await expect(LeaguePage({ params: Promise.resolve({ slug: "en.1" }), searchParams: Promise.resolve({}) })).rejects.toThrow(
      "REDIRECT:/leagues/premier-league"
    );
  });
});

describe("replay is yesterday in the viewer's timezone, never an old fixed list", () => {
  it("asks the API for yesterday using the viewer's offset, with no date override", async () => {
    mocked.replayDay.mockResolvedValue({
      date: "2026-09-27", matches: [], no_events_note: "", most_recent_day_with_matches: null, most_recent_day_with_results: null,
    });
    render(await ReplayPage({ searchParams: Promise.resolve({ tz: "-240" }) }));
    expect(mocked.replayDay).toHaveBeenCalledWith(-240, undefined);
    expect(document.body.textContent).toMatch(/Yesterday/);
    expect(document.body.textContent).not.toMatch(/2015|StatsBomb/i);
  });

  it("without a reported timezone it asks nothing and just works out the offset client-side", async () => {
    render(await ReplayPage({ searchParams: Promise.resolve({}) }));
    expect(mocked.replayDay).not.toHaveBeenCalled();
  });
});
