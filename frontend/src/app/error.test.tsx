import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./error";

afterEach(() => vi.unstubAllGlobals());

describe("app error boundary (the free backend waking up)", () => {
  it("says the server is waking up and never shows a raw error message", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<ErrorBoundary error={new Error("TypeError: fetch failed at /leagues")} reset={vi.fn()} />);
    expect(screen.getByText("Waking up the server")).toBeTruthy();
    expect(screen.getByText(/up to a minute/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/TypeError|fetch failed/);
  });

  it("retries by itself: re-renders the page as soon as /health answers", async () => {
    const reset = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ErrorBoundary error={new Error("x")} reset={reset} />);
    await waitFor(() => expect(reset).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/health$/);
  });
});
