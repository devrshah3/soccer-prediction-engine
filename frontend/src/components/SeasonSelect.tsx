"use client";

import { useRouter } from "next/navigation";

export function SeasonSelect({ slug, season, seasons }: { slug: string; season: string; seasons: string[] }) {
  const router = useRouter();
  return (
    <select
      value={season}
      onChange={(e) => router.push(`/leagues/${slug}?season=${e.target.value}`)}
      className="glass-row px-3 py-1.5 text-sm text-foreground outline-none transition-colors focus:border-accent"
    >
      {seasons.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
