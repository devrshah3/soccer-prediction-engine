// Flag emoji by country, not by league code: this is what actually disambiguates "Ligue 1"
// vs "Serie B" for a skimming user. No icon-asset pipeline exists yet, so an emoji flag is
// the pragmatic choice (England uses the UK flag - the dedicated England tag-sequence emoji
// doesn't render everywhere).
const FLAGS: Record<string, string> = {
  England: "\u{1F1EC}\u{1F1E7}",
  Spain: "\u{1F1EA}\u{1F1F8}",
  Italy: "\u{1F1EE}\u{1F1F9}",
  Germany: "\u{1F1E9}\u{1F1EA}",
  France: "\u{1F1EB}\u{1F1F7}",
};

export function LeagueChip({ name, country }: { name: string; country: string | null }) {
  const flag = country ? FLAGS[country] : "\u{1F310}"; // globe for international
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
      <span>{flag}</span>
      {name}
    </span>
  );
}
