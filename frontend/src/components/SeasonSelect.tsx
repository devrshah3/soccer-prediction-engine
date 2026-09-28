"use client";

import { useRouter } from "next/navigation";

export function SeasonSelect({ basePath, season, seasons }: { basePath: string; season: string; seasons: string[] }) {
  const router = useRouter();
  return (
    <select
      value={season}
      onChange={(e) => router.push(`${basePath}?season=${e.target.value}`)}
      className="glass-float rounded-2xl border border-white/15 px-3 py-1.5 text-sm text-foreground outline-none transition-colors focus:border-accent"
    >
      {seasons.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
