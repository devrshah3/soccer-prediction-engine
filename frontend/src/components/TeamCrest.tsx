// No crest-image pipeline exists (see MORNING_REPORT.md) - a deterministic initials badge
// is the honest stand-in rather than a placeholder image or a guessed asset URL.
const PALETTE = [
  ["#1d4ed8", "#60a5fa"],
  ["#0f766e", "#2dd4bf"],
  ["#7c3aed", "#a78bfa"],
  ["#be123c", "#fb7185"],
  ["#b45309", "#fbbf24"],
  ["#4338ca", "#818cf8"],
  ["#0e7490", "#22d3ee"],
  ["#15803d", "#4ade80"],
] as const;

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return h;
}

function initials(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

const SIZES = { sm: "h-6 w-6 text-[10px]", md: "h-9 w-9 text-xs", lg: "h-14 w-14 text-lg" };

export function TeamCrest({ name, size = "md" }: { name: string; size?: keyof typeof SIZES }) {
  const [from, to] = PALETTE[hash(name) % PALETTE.length];
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-bold text-white shadow-inner ring-1 ring-white/10 ${SIZES[size]}`}
      style={{ backgroundImage: `linear-gradient(135deg, ${from}, ${to})` }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
