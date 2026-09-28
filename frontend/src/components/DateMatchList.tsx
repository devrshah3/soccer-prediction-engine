"use client";

import { useState } from "react";
import type { League, MatchOnDate } from "@/lib/api";
import { MatchRow } from "./MatchRow";

// B.6: matches for a selected date, grouped by competition, with a client-side league
// filter (no extra round trip - the whole day's matches are already fetched).
export function DateMatchList({ matches, leagues }: { matches: MatchOnDate[]; leagues: Map<string, League> }) {
  const [filter, setFilter] = useState<string | null>(null);
  const presentCodes = Array.from(new Set(matches.map((m) => m.league_code)));
  const visible = filter ? matches.filter((m) => m.league_code === filter) : matches;

  const grouped = new Map<string, MatchOnDate[]>();
  for (const m of visible) {
    const arr = grouped.get(m.league_code) ?? [];
    arr.push(m);
    grouped.set(m.league_code, arr);
  }

  return (
    <div className="space-y-6">
      {presentCodes.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setFilter(null)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              filter === null
                ? "border-accent/50 bg-accent-soft text-accent-text"
                : "border-border-strong bg-surface-raised text-muted hover:text-foreground"
            }`}
          >
            All
          </button>
          {presentCodes.map((code) => (
            <button
              key={code}
              onClick={() => setFilter(code)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                filter === code
                  ? "border-accent/50 bg-accent-soft text-accent-text"
                  : "border-border-strong bg-surface-raised text-muted hover:text-foreground"
              }`}
            >
              {leagues.get(code)?.name ?? code}
            </button>
          ))}
        </div>
      )}
      {[...grouped.entries()].map(([code, ms]) => (
        <div key={code}>
          <h2 className="mb-3 text-sm font-semibold text-muted">{leagues.get(code)?.name ?? code}</h2>
          <div className="grid gap-3.5 sm:grid-cols-2">
            {ms.map((m) => (
              <MatchRow
                key={m.id}
                match={m}
                league={leagues.get(m.league_code)}
                prediction={m.prediction}
                longRange={m.long_range}
                dateMayChange={m.date_may_change}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
