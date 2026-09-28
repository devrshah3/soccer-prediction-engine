"use client";

import { useState } from "react";
import Link from "next/link";
import { FormDots } from "./FormDots";
import { Sheet } from "./glass/Sheet";
import type { Standings, TrophyOdds } from "@/lib/api";

// Item 3: the "Points table" button + Sheet. The caller never renders this at all when a
// table can't be computed for the current selection (see leagues/[slug]/page.tsx) - there
// is no "empty table" state here by design, per the task's explicit "hide the button
// entirely" instruction.
export function LeagueTableSheet({
  leagueName,
  standings,
  trophyOdds,
  showZoneMarkers,
  initialOpen,
}: {
  leagueName: string;
  standings: Standings;
  trophyOdds: TrophyOdds | null;
  showZoneMarkers: boolean;
  initialOpen: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  const [tab, setTab] = useState<"table" | "odds">("table");
  const relegationStart = standings.table.length - 3;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="glass-row flex items-center gap-2 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-white/[0.08]"
      >
        <TableIcon className="h-4 w-4 text-accent" />
        Points table
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title={`${leagueName} · ${standings.season}`}>
        {trophyOdds && (
          <div className="mb-4 flex gap-1.5">
            <TabButton active={tab === "table"} onClick={() => setTab("table")}>
              Table
            </TabButton>
            <TabButton active={tab === "odds"} onClick={() => setTab("odds")}>
              Title odds
            </TabButton>
          </div>
        )}
        {tab === "table" || !trophyOdds ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wide text-muted-2">
                <tr>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">Team</th>
                  <th className="px-2 py-2 text-right font-medium">P</th>
                  <th className="px-2 py-2 text-right font-medium">W</th>
                  <th className="px-2 py-2 text-right font-medium">D</th>
                  <th className="px-2 py-2 text-right font-medium">L</th>
                  <th className="px-2 py-2 text-right font-medium">GF</th>
                  <th className="px-2 py-2 text-right font-medium">GA</th>
                  <th className="px-2 py-2 text-right font-medium">GD</th>
                  <th className="px-2 py-2 pr-3 text-right font-medium text-foreground">Pts</th>
                  <th className="px-2 py-2 font-medium">Form</th>
                </tr>
              </thead>
              <tbody>
                {standings.table.map((row) => (
                  <tr key={row.team_id} className="border-t border-white/10 transition-colors hover:bg-white/[0.06]">
                    <td className="px-3 py-2 tabular-nums text-muted-2">
                      <span className="flex items-center gap-1.5">
                        {showZoneMarkers && row.position <= 4 && (
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" title="Top 4" />
                        )}
                        {showZoneMarkers && row.position > relegationStart && (
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger" title="Relegation zone" />
                        )}
                        {row.position}
                      </span>
                    </td>
                    <td className="px-2 py-2">
                      <Link
                        href={`/teams/${encodeURIComponent(row.team_id)}`}
                        onClick={() => setOpen(false)}
                        className="font-medium text-foreground hover:text-accent"
                      >
                        {row.team_name}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.played}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.w}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.d}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.l}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.gf}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.ga}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted">{row.gd}</td>
                    <td className="px-2 py-2 pr-3 text-right font-bold tabular-nums text-foreground">{row.pts}</td>
                    <td className="px-2 py-2">
                      <FormDots form={row.form} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="mb-3 text-xs text-muted-2">
              Monte Carlo simulation of the rest of the season ({trophyOdds.n_sims.toLocaleString()} runs over{" "}
              {trophyOdds.remaining_fixtures} remaining fixtures). Not a promise of accuracy.
            </p>
            {trophyOdds.teams.map((t) => (
              <Link
                key={t.team_id}
                href={`/teams/${encodeURIComponent(t.team_id)}`}
                onClick={() => setOpen(false)}
                className="glass-row flex items-center justify-between gap-3 px-3 py-2 text-sm transition-colors hover:bg-white/[0.08]"
              >
                <span className="truncate font-medium text-foreground">{t.team_name}</span>
                <span className="flex shrink-0 gap-3 text-xs tabular-nums text-muted-2">
                  <span>Title {(t.title_pct * 100).toFixed(1)}%</span>
                  <span>Top 4 {(t.top4_pct * 100).toFixed(1)}%</span>
                  <span className="text-danger">Rel. {(t.relegation_pct * 100).toFixed(1)}%</span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </Sheet>
    </>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? "bg-gradient-to-r from-accent to-accent-2 text-accent-foreground" : "glass-row text-muted hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function TableIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 10h18M9 10v10" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
