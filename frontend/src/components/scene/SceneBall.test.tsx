import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const dispose = vi.fn();
const createBall = vi.fn();

vi.mock("./ballScene", () => ({ createBall: (...args: unknown[]) => createBall(...args) }));

import { SceneBall } from "./SceneBall";

function stubEnvironment({ wide = true, reduced = false, saveData = false } = {}) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("min-width") ? wide : query.includes("reduced-motion") ? reduced : false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  Object.defineProperty(navigator, "connection", { value: { saveData }, configurable: true });
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
}

beforeEach(() => {
  createBall.mockReset();
  dispose.mockReset();
  createBall.mockImplementation(() => ({ resize: vi.fn(), setActive: vi.fn(), dispose }));
});
afterEach(() => vi.unstubAllGlobals());

describe("SceneBall guard rails", () => {
  it("loads the 3D ball on a wide viewport with motion allowed, and disposes it on unmount", async () => {
    stubEnvironment();
    const { unmount, container } = render(<SceneBall />);
    await waitFor(() => expect(createBall).toHaveBeenCalledTimes(1));
    expect(container.querySelector("canvas")).toBeTruthy();
    unmount();
    expect(dispose).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["a phone-width viewport", { wide: false }],
    ["reduced motion", { reduced: true }],
    ["Save-Data", { saveData: true }],
  ])("never even loads the 3D chunk for %s", async (_label, env) => {
    stubEnvironment(env);
    render(<SceneBall />);
    await new Promise((r) => setTimeout(r, 30));
    expect(createBall).not.toHaveBeenCalled();
  });

  it("always renders the static ball image (same spot) as the fallback", () => {
    stubEnvironment({ wide: false });
    const { container } = render(<SceneBall />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("/scene/ball.webp");
    expect(img?.getAttribute("alt")).toBe("");
  });

  it("keeps the static image when WebGL fails, without crashing", async () => {
    stubEnvironment();
    createBall.mockImplementation(() => {
      throw new Error("no webgl");
    });
    const { container } = render(<SceneBall />);
    await waitFor(() => expect(createBall).toHaveBeenCalled());
    expect(container.querySelector("canvas")).toBeNull();
    expect(container.querySelector("img")).toBeTruthy();
  });
});
