const COLOR: Record<string, string> = {
  W: "bg-emerald-500 text-emerald-950",
  D: "bg-zinc-500 text-zinc-950",
  L: "bg-red-500/80 text-red-950",
};

export function FormDots({ form }: { form: ("W" | "D" | "L")[] | null | undefined }) {
  if (!form || form.length === 0) return <span className="text-xs text-zinc-500">-</span>;
  return (
    <div className="flex gap-1">
      {form.map((r, i) => (
        <span
          key={i}
          className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${COLOR[r]}`}
        >
          {r}
        </span>
      ))}
    </div>
  );
}
