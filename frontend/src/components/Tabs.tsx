"use client";

import { useState } from "react";

export function Tabs({ tabs }: { tabs: { label: string; content: React.ReactNode }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div>
      <div className="flex gap-1 overflow-x-auto border-b border-border">
        {tabs.map((t, i) => (
          <button
            key={t.label}
            onClick={() => setActive(i)}
            className={`relative shrink-0 px-4 py-2.5 text-sm font-medium transition-colors ${
              active === i ? "text-foreground" : "text-muted hover:text-foreground"
            }`}
          >
            {t.label}
            {active === i && <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-accent" />}
          </button>
        ))}
      </div>
      <div className="pt-5">{tabs[active].content}</div>
    </div>
  );
}
