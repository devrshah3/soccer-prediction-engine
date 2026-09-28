"use client";

import { useState } from "react";
import type { PredictionSummary } from "@/lib/api";
import { timeAgo } from "@/lib/time";

// D.11: cards show only league/teams/time-or-result/probability bar - everything else
// (model version, evidence tier, when it was computed, the data cutoff) lives behind this
// (i) icon instead of cluttering every card. Stops the click from also triggering the
// card's own <Link> navigation (this is always rendered inside one).
export function PredictionInfoPopover({ prediction }: { prediction: PredictionSummary }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-label="Prediction details"
        aria-expanded={open}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-border-strong text-[10px] font-bold text-muted-2 transition-colors hover:border-accent/50 hover:text-foreground"
      >
        i
      </button>
      {open && (
        <div
          role="dialog"
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 z-20 mt-1.5 w-56 space-y-1.5 rounded-lg border border-border-strong bg-surface-raised p-3 text-left text-xs shadow-xl"
        >
          <p className="font-medium text-foreground">Prediction details</p>
          <p className="text-muted">Model: {prediction.model_version}</p>
          <p className="text-muted">Evidence tier: {prediction.evidence}</p>
          <p className="text-muted">Data cutoff: {prediction.as_of}</p>
          {prediction.computed_at && (
            <p className="text-muted-2">Computed {timeAgo(prediction.computed_at)}</p>
          )}
        </div>
      )}
    </span>
  );
}
