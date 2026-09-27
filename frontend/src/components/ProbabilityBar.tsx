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

  return (
    <div className="w-full">
      {size === "lg" && (
        <div className="mb-2 flex items-baseline justify-between text-sm font-medium text-foreground">
          <span className="truncate">{homeLabel}</span>
          <span className="truncate text-right">{awayLabel}</span>
        </div>
      )}
      <div className={`flex w-full overflow-hidden rounded-full bg-surface-raised ring-1 ring-inset ring-border ${barHeight}`}>
        <div
          className="bg-gradient-to-r from-accent to-accent-hover transition-[width]"
          style={{ width: pct(home) }}
          title={`${homeLabel} win ${pct(home)}`}
        />
        <div className="bg-muted-2/70 transition-[width]" style={{ width: pct(draw) }} title={`Draw ${pct(draw)}`} />
        <div
          className="bg-gradient-to-r from-zinc-400 to-zinc-300 transition-[width]"
          style={{ width: pct(away) }}
          title={`${awayLabel} win ${pct(away)}`}
        />
      </div>
      <div className={`mt-1.5 flex justify-between ${size === "lg" ? "text-sm" : "text-xs"} text-muted`}>
        <span className="font-semibold text-accent">{pct(home)}</span>
        <span>{pct(draw)}</span>
        <span className="font-semibold text-zinc-300">{pct(away)}</span>
      </div>
    </div>
  );
}
