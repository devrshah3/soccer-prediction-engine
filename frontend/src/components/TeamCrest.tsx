// No crest-image pipeline exists, and item 5 of the glass redesign explicitly forbids any
// club/league logo - a glass initials circle is the deliberate choice, not a fallback. A
// deterministic per-team tint (a colored glow/ring, not a solid fill) keeps teams visually
// distinguishable at a glance without breaking the glass look.
const TINTS = [
  "#60a5fa", "#2dd4bf", "#a78bfa", "#fb7185", "#fbbf24", "#818cf8", "#22d3ee", "#4ade80",
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
  const tint = TINTS[hash(name) % TINTS.length];
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full border font-bold text-foreground ${SIZES[size]}`}
      style={{
        background: "linear-gradient(135deg, rgba(255,255,255,0.16), rgba(255,255,255,0.04)), rgba(7,14,36,0.7)",
        borderColor: `${tint}55`,
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.25), 0 0 10px ${tint}33`,
      }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
