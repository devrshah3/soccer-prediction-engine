"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// While at least one match on the page is live, re-run the server component every minute so
// the score / goal list / "updated X min ago" pick up whatever the backend poller (every ~10
// min, within API-Football's 100/day budget) has written since. It only re-reads OUR
// database - it never triggers a provider call - and pauses while the tab is hidden.
export const LIVE_REFRESH_MS = 60_000;

export function LiveAutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, LIVE_REFRESH_MS);
    return () => clearInterval(id);
  }, [active, router]);
  return null;
}
