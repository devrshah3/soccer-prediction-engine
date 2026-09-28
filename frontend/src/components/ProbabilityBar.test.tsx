import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProbabilityBar } from "./ProbabilityBar";

const segments = (c: HTMLElement) => Array.from(c.querySelectorAll<HTMLElement>('[role="img"] > div'));

describe("ProbabilityBar outcome colours", () => {
  it("home is always blue, draw amber, away rose - whichever outcome leads", () => {
    for (const [h, d, a] of [[0.6, 0.25, 0.15], [0.2, 0.5, 0.3], [0.2, 0.2, 0.6]]) {
      const { container, unmount } = render(<ProbabilityBar home={h} draw={d} away={a} homeLabel="Finland" awayLabel="Belarus" />);
      const [home, draw, away] = segments(container);
      expect(home.style.background).toContain("--out-home-from");
      expect(draw.style.background).toContain("--out-draw-from");
      expect(away.style.background).toContain("--out-away-from");
      unmount();
    }
  });

  it("only the most likely outcome is full brightness with a glow; the others are dimmed but present", () => {
    const { container } = render(<ProbabilityBar home={0.2} draw={0.5} away={0.3} homeLabel="A" awayLabel="B" />);
    const [home, draw, away] = segments(container);
    expect(draw.style.opacity).toBe("1");
    expect(draw.style.boxShadow).toContain("--out-draw-glow");
    expect(home.style.opacity).toBe("0.72");
    expect(away.style.opacity).toBe("0.72");
    expect(home.style.boxShadow).toBe("");
  });

  it("never relies on colour alone: every outcome is labelled with its percentage", () => {
    render(<ProbabilityBar home={0.52} draw={0.27} away={0.22} homeLabel="Finland" awayLabel="Belarus" />);
    expect(screen.getByText(/Finland/).textContent).toContain("52%");
    expect(screen.getByText(/Draw/).textContent).toContain("27%");
    expect(screen.getByText(/Belarus/).textContent).toContain("22%");
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Finland 52%, draw 27%, Belarus 22%");
  });
});
