"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";

const RANGE_DAYS = 90;

function isoDaysFromToday(offset: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

function nextWeekday(targetDow: number): string {
  const d = new Date();
  const diff = (targetDow - d.getUTCDay() + 7) % 7 || 7;
  d.setUTCDate(d.getUTCDate() + diff);
  return d.toISOString().slice(0, 10);
}

// B.6: prev/next day arrows, a native date input as the calendar popover (a real
// browser-native calendar, not a custom-built one - simpler and fully accessible for
// free), and quick chips. Keeps the selected date in the URL (?date=YYYY-MM-DD); no date
// param at all means "today, with automatic rollover" (see page.tsx).
export function DatePicker({ selected, basePath = "/" }: { selected: string; basePath?: string }) {
  const router = useRouter();
  const today = useMemo(() => isoDaysFromToday(0), []);
  const min = useMemo(() => isoDaysFromToday(-RANGE_DAYS), []);
  const max = useMemo(() => isoDaysFromToday(RANGE_DAYS), []);

  function go(date: string) {
    if (date === today) {
      router.push(basePath);
    } else {
      router.push(`${basePath}?date=${date}`);
    }
  }

  function shiftDay(delta: number) {
    const d = new Date(`${selected}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + delta);
    go(d.toISOString().slice(0, 10));
  }

  const chips: { label: string; date: string }[] = [
    { label: "Today", date: today },
    { label: "Tomorrow", date: isoDaysFromToday(1) },
    { label: "Sat", date: nextWeekday(6) },
    { label: "Sun", date: nextWeekday(0) },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-border-strong bg-surface-raised p-1">
        <button
          onClick={() => shiftDay(-1)}
          aria-label="Previous day"
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface hover:text-foreground"
        >
          &larr;
        </button>
        <input
          type="date"
          value={selected}
          min={min}
          max={max}
          onChange={(e) => e.target.value && go(e.target.value)}
          className="rounded-md bg-transparent px-2 py-1 text-sm text-foreground outline-none"
        />
        <button
          onClick={() => shiftDay(1)}
          aria-label="Next day"
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface hover:text-foreground"
        >
          &rarr;
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c) => (
          <button
            key={c.label}
            onClick={() => go(c.date)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              selected === c.date
                ? "border-accent/50 bg-accent-soft text-accent"
                : "border-border-strong bg-surface-raised text-muted hover:text-foreground"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}
