import { Flag } from "./Flag";

// Real drawn flag (never emoji - see Flag.tsx) for the country that disambiguates
// "Ligue 1" vs "Serie A" for a skimming user; a neutral icon (Flag's own fallback) for a
// continental competition with no single country.
export function LeagueChip({ name, country }: { name: string; country: string | null }) {
  return (
    <span className="glass-row inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-muted">
      <Flag country={country} className="h-[13px] w-[18px] shrink-0 rounded-[2px]" />
      {name}
    </span>
  );
}
