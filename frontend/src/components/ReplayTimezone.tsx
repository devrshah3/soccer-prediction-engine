"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { tzOffsetMinutesEast } from "@/lib/replayDate";

// Replay's "yesterday" is the viewer's LOCAL yesterday, and only the browser knows the
// timezone - so on a first visit (no ?tz=) this reports the offset and swaps the URL.
export function ReplayTimezone({ date }: { date?: string }) {
  const router = useRouter();
  useEffect(() => {
    const qs = new URLSearchParams({ tz: String(tzOffsetMinutesEast()) });
    if (date) qs.set("date", date);
    router.replace(`/replay?${qs.toString()}`);
  }, [router, date]);

  return (
    <div className="glass p-8 text-center">
      <p className="text-sm text-muted">Finding yesterday&apos;s matches for your timezone&hellip;</p>
      <noscript>
        <Link href="/replay?tz=0" className="mt-2 inline-block text-sm text-accent hover:underline">
          Continue with UTC dates
        </Link>
      </noscript>
    </div>
  );
}
