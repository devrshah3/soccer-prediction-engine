"use client";

import { useState } from "react";

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
      <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

// Search is still a placeholder (disabled input). On desktop it is a glass field; on phones
// it collapses to an icon button that expands into a field over the top bar when tapped.
export function SearchBox() {
  const [open, setOpen] = useState(false);
  const field = (
    <label className="glass-float flex items-center gap-2 rounded-full border border-white/15 px-3 py-2 text-xs text-muted">
      <SearchIcon className="h-3.5 w-3.5 shrink-0" />
      <input
        type="search"
        placeholder="Search teams, leagues..."
        disabled
        className="w-full min-w-0 bg-transparent text-foreground outline-none placeholder:text-muted-2 sm:w-44"
        aria-label="Search (coming soon)"
      />
    </label>
  );

  return (
    <div className="pointer-events-auto flex justify-end">
      <div className="hidden sm:block">{field}</div>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close search" : "Open search"}
        aria-expanded={open}
        className="glass glass-float flex h-9 w-9 items-center justify-center !rounded-full text-muted hover:text-foreground sm:hidden"
      >
        <SearchIcon className="h-4 w-4" />
      </button>
      {open && <div className="absolute inset-x-3 top-14 z-50 sm:hidden">{field}</div>}
    </div>
  );
}
