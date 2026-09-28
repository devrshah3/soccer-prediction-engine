"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POLL_EVERY_MS = 3000;
const GIVE_UP_AFTER_MS = 90_000;

// The app-level error boundary. Almost every failure a visitor can hit is the free backend waking up,
// so instead of a blank page or a raw error this says so and retries on its own: it pings /health
// (which also nudges the sleeping server awake) and re-renders the page the moment it answers.
export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const [gaveUp, setGaveUp] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const started = Date.now();
    async function poll() {
      while (!cancelled && Date.now() - started < GIVE_UP_AFTER_MS) {
        try {
          const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000), cache: "no-store" });
          if (res.ok) {
            if (!cancelled) reset();
            return;
          }
        } catch {
          /* still asleep - keep waiting */
        }
        await new Promise((r) => setTimeout(r, POLL_EVERY_MS));
      }
      if (!cancelled) setGaveUp(true);
    }
    void poll();
    return () => {
      cancelled = true;
    };
  }, [reset, attempt]);

  return (
    <div role="status" aria-live="polite" className="glass mx-auto mt-10 max-w-lg p-8 text-center">
      {gaveUp ? (
        <>
          <h1 className="text-lg font-semibold text-foreground">Still can&apos;t reach the server</h1>
          <p className="mt-2 text-sm text-muted">
            It may be restarting or having a bad moment. Give it a couple of minutes and try again.
          </p>
          <button
            onClick={() => {
              setGaveUp(false);
              setAttempt((n) => n + 1);
            }}
            className="glass-float mt-4 rounded-full border border-white/15 px-4 py-2 text-sm text-foreground hover:border-white/30"
          >
            Try again
          </button>
        </>
      ) : (
        <>
          <h1 className="text-lg font-semibold text-foreground">Waking up the server</h1>
          <p className="mt-2 text-sm text-muted">This can take up to a minute. The page will load by itself.</p>
          <div className="mx-auto mt-5 h-1.5 w-40 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-gradient-to-r from-accent to-accent-2" />
          </div>
        </>
      )}
    </div>
  );
}
