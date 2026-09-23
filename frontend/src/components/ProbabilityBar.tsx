export function ProbabilityBar({
  home,
  draw,
  away,
  homeLabel,
  awayLabel,
}: {
  home: number;
  draw: number;
  away: number;
  homeLabel: string;
  awayLabel: string;
}) {
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <div className="w-full">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-zinc-800">
        <div className="bg-emerald-500" style={{ width: pct(home) }} title={`${homeLabel} win ${pct(home)}`} />
        <div className="bg-zinc-500" style={{ width: pct(draw) }} title={`Draw ${pct(draw)}`} />
        <div className="bg-zinc-300" style={{ width: pct(away) }} title={`${awayLabel} win ${pct(away)}`} />
      </div>
      <div className="mt-1 flex justify-between text-xs text-zinc-400">
        <span className="text-emerald-400">{pct(home)}</span>
        <span>{pct(draw)}</span>
        <span className="text-zinc-300">{pct(away)}</span>
      </div>
    </div>
  );
}
