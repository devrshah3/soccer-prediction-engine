import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CardEvent } from "@/lib/api";
import { CardList } from "./CardList";

const home = { id: "city", name: "Man City" };
const away = { id: "united", name: "Man United" };

describe("cards", () => {
  const cards: CardEvent[] = [
    { team_id: "united", player: "Casemiro", minute: 23, card: "yellow" },
    { team_id: "city", player: "Rodri", minute: 58, card: "red" },
  ];

  it("renders yellow and red cards with minute, player and team", () => {
    render(<CardList cards={cards} home={home} away={away} />);
    expect(screen.getByRole("img", { name: "Yellow card" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Red card" })).toBeTruthy();
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual(["23'Casemiro — Man United", "58'Rodri — Man City"]);
  });

  it("renders no cards section at all when there are none", () => {
    const { container } = render(<CardList cards={[]} home={home} away={away} />);
    expect(container.innerHTML).toBe("");
    const none = render(<CardList cards={undefined} home={home} away={away} />);
    expect(none.container.innerHTML).toBe("");
  });
});
