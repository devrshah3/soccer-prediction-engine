const COLOR: Record<string, string> = {
  W: "bg-success/20 text-success ring-1 ring-inset ring-success/40",
  D: "bg-muted-2/20 text-muted ring-1 ring-inset ring-border-strong",
  L: "bg-danger/20 text-danger ring-1 ring-inset ring-danger/40",
};

export function FormDots({ form }: { form: ("W" | "D" | "L")[] | null | undefined }) {
  if (!form || form.length === 0) return <span className="text-xs text-muted">&ndash;</span>;
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
