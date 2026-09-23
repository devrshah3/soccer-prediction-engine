"use client";

import { useRouter } from "next/navigation";

export function SeasonSelect({ code, season, seasons }: { code: string; season: string; seasons: string[] }) {
  const router = useRouter();
  return (
    <select
      value={season}
      onChange={(e) => router.push(`/leagues/${code}?season=${e.target.value}`)}
      className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-200"
    >
      {seasons.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
