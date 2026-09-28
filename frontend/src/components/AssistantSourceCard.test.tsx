import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssistantSourceCard } from "./AssistantSourceCard";

// Item 4 regression: the standings source card used to print the raw league_code
// ("en.1") next to a player/team's position - a raw internal code must never reach a
// rendered page.
describe("AssistantSourceCard raw-code leak", () => {
  it("shows the league's display name, never its raw code", () => {
    render(
      <AssistantSourceCard
        source={{
          type: "kickcast_standings",
          data: { team_id: "arsenal", team_name: "Arsenal", league_code: "en.1", season: "2026-27", position: 1, pts: 20 },
        }}
      />
    );
    expect(screen.getByText(/Premier League/)).toBeTruthy();
    expect(screen.queryByText(/en\.1/)).toBeNull();
  });
});
