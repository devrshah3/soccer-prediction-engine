type Outcome = "home" | "draw" | "away";

// Each outcome has ONE fixed colour on every bar (tokens --out-home/--out-draw/--out-away in
// globals.css): home = blue (left), draw = amber, away = rose (right). The most likely
// segment is full brightness with a soft glow; the other two stay clearly coloured but
// dimmed. Colour is never the only signal - the row below names each outcome with a dot,
// a label and a percentage.
const STYLE: Record<Outcome, { gradient: string; glow: string; dot: string }> = {
  home: {
    gradient: "linear-gradient(90deg, var(--out-home-from), var(--out-home-to))",
    glow: "var(--out-home-glow)",
    dot: "var(--out-home-to)",
  },
  draw: {
    gradient: "linear-gradient(90deg, var(--out-draw-from), var(--out-draw-to))",
    glow: "var(--out-draw-glow)",
    dot: "var(--out-draw-to)",
  },
  away: {
    gradient: "linear-gradient(90deg, var(--out-away-from), var(--out-away-to))",
    glow: "var(--out-away-glow)",
    dot: "var(--out-away-to)",
  },
};

export function ProbabilityBar({
  home,
  draw,
  away,
  homeLabel,
  awayLabel,
  size = "sm",
}: {
  home: number;
  draw: number;
  away: number;
  homeLabel: string;
  awayLabel: string;
  size?: "sm" | "lg";
}) {
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const barHeight = size === "lg" ? "h-4" : "h-2.5";
  const leader: Outcome = home >= draw && home >= away ? "home" : draw >= away ? "draw" : "away";
  const values: Record<Outcome, number> = { home, draw, away };
  const names: Record<Outcome, string> = { home: homeLabel, draw: "Draw", away: awayLabel };

  const segment = (o: Outcome) => (
    <div
      key={o}
      className="transition-[width]"
      style={{
        width: pct(values[o]),
        background: STYLE[o].gradient,
        opacity: o === leader ? 1 : 0.72,
        boxShadow: o === leader ? `0 0 12px ${STYLE[o].glow}` : undefined,
      }}
      title={`${o === "draw" ? "Draw" : `${names[o]} win`} ${pct(values[o])}`}
    />
  );

  const legend = (o: Outcome, align: string) => (
    <span
      key={o}
      className={`flex min-w-0 items-center gap-1.5 ${align} ${o === leader ? "font-semibold text-foreground" : ""}`}
      title={`${names[o]} ${pct(values[o])}`}
    >
      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ background: STYLE[o].dot }} />
      <span className="truncate">
        {names[o]} <span className="tabular-nums">{pct(values[o])}</span>
      </span>
    </span>
  );

  return (
    <div className="w-full">
      <div
        role="img"
        aria-label={`${homeLabel} ${pct(home)}, draw ${pct(draw)}, ${awayLabel} ${pct(away)}`}
        className={`flex w-full gap-px overflow-hidden rounded-full border border-white/10 bg-white/[0.05] ${barHeight}`}
      >
        {segment("home")}
        {segment("draw")}
        {segment("away")}
      </div>
      <div className={`mt-2 grid grid-cols-[1fr_auto_1fr] gap-x-3 ${size === "lg" ? "text-sm" : "text-xs"} text-muted`}>
        {legend("home", "justify-start")}
        {legend("draw", "justify-center")}
        {legend("away", "justify-end")}
      </div>
    </div>
  );
}
