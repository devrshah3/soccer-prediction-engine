"use client";

import { useRouter } from "next/navigation";

export function SeasonSelect({ code, season, seasons }: { code: string; season: string; seasons: string[] }) {
  const router = useRouter();
  return (
    <select
      value={season}
      onChange={(e) => router.push(`/leagues/${code}?season=${e.target.value}`)}
      className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-foreground shadow-sm outline-none transition-colors focus:border-accent"
    >
      {seasons.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
