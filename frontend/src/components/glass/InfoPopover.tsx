"use client";

import { useState } from "react";

// Item 5: the reusable (i) popover for a card's source/season/method details - keeps a
// card itself to the essentials and puts provenance one click away, same pattern as
// PredictionInfoPopover but generic (title + plain lines) for reuse anywhere else a card
// needs to declutter this way.
export function InfoPopover({ label, title, lines }: { label: string; title: string; lines: string[] }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-label={label}
        aria-expanded={open}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-white/20 text-[10px] font-bold text-muted-2 transition-colors hover:border-accent/50 hover:text-foreground"
      >
        i
      </button>
      {open && (
        <div
          role="dialog"
          onClick={(e) => e.stopPropagation()}
          className="glass absolute right-0 z-20 mt-1.5 w-60 space-y-1.5 !rounded-xl p-3 text-left text-xs"
        >
          <p className="font-medium text-foreground">{title}</p>
          {lines.map((line) => (
            <p key={line} className="text-muted">
              {line}
            </p>
          ))}
        </div>
      )}
    </span>
  );
}
