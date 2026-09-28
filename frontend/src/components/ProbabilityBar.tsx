// Glass spec: the LEADING outcome (whichever of home/draw/away is highest) is bright blue
// with a soft glow; the other two segments are neutral glass fills - not a fixed
// home=blue/away=grey scheme, since "leading" can be any of the three.
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
  const barHeight = size === "lg" ? "h-4" : "h-2";
  const leader = home >= draw && home >= away ? "home" : draw >= away ? "draw" : "away";

  const segmentClass = (segment: "home" | "draw" | "away") =>
    segment === leader
      ? "bg-gradient-to-r from-accent to-accent-2 shadow-[0_0_12px_var(--accent-glow)]"
      : "bg-white/[0.14]";

  return (
    <div className="w-full">
      {size === "lg" && (
        <div className="mb-2 flex items-baseline justify-between text-sm font-medium text-foreground">
          <span className="truncate">{homeLabel}</span>
          <span className="truncate text-right">{awayLabel}</span>
        </div>
      )}
      <div className={`flex w-full overflow-hidden rounded-full border border-white/10 bg-white/[0.05] ${barHeight}`}>
        <div className={`transition-[width] ${segmentClass("home")}`} style={{ width: pct(home) }} title={`${homeLabel} win ${pct(home)}`} />
        <div className={`transition-[width] ${segmentClass("draw")}`} style={{ width: pct(draw) }} title={`Draw ${pct(draw)}`} />
        <div className={`transition-[width] ${segmentClass("away")}`} style={{ width: pct(away) }} title={`${awayLabel} win ${pct(away)}`} />
      </div>
      <div className={`mt-1.5 flex justify-between ${size === "lg" ? "text-sm" : "text-xs"} text-muted`}>
        <span className={leader === "home" ? "font-semibold text-accent-2" : ""}>{pct(home)}</span>
        <span className={leader === "draw" ? "font-semibold text-accent-2" : ""}>{pct(draw)}</span>
        <span className={leader === "away" ? "font-semibold text-accent-2" : ""}>{pct(away)}</span>
      </div>
    </div>
  );
}
