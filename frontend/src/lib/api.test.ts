import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, BackendUnavailableError } from "./api";

afterEach(() => vi.unstubAllGlobals());

const respond = (status: number, body: unknown = []) => new Response(JSON.stringify(body), { status });

describe("apiFetch against a sleeping backend", () => {
  it("turns a network failure or timeout into BackendUnavailableError, never a raw error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(api.leagues()).rejects.toBeInstanceOf(BackendUnavailableError);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("timed out", "TimeoutError")));
    await expect(api.leagues()).rejects.toBeInstanceOf(BackendUnavailableError);
  });

  it.each([502, 503, 504])("treats HTTP %i (a waking host) as unavailable", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(status)));
    await expect(api.leagues()).rejects.toBeInstanceOf(BackendUnavailableError);
  });

  it("keeps real errors distinct: a 404 is an ApiError so pages can show notFound()", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(404)));
    const err = await api.leagues().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
  });

  it("asks for a short-lived cache and sets a timeout so visitors see last good data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, [{ code: "en.1" }]));
    vi.stubGlobal("fetch", fetchMock);
    await api.leagues();
    const init = fetchMock.mock.calls[0][1];
    expect(init.next).toEqual({ revalidate: 60 });
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.cache).toBeUndefined(); // not no-store
  });
});
