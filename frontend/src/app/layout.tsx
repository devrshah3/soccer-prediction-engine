import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ChatWidget } from "@/components/ChatWidget";
import { MobileNav } from "@/components/MobileNav";
import { NavLink } from "@/components/NavLink";
import { SceneBackground } from "@/components/SceneBackground";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/time";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "KickCast",
  description: "Free soccer scores, fixtures, and our own match predictions.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  let leagues: { code: string; name: string; kind: string }[] = [];
  try {
    leagues = await api.leagues();
  } catch {
    // backend not reachable (e.g. during a frontend-only lint/build check) - nav degrades gracefully
  }
  const domesticLeagues = leagues.filter((l) => l.kind === "domestic_league");
  // Champions League only shown once real data exists (FOOTBALL_DATA_ORG_API_KEY set and
  // scripts/ingest.py run) - never link to an empty/404ing page, per "don't build UI for
  // data we don't have".
  const hasChampionsLeague = leagues.some((l) => l.code === "CL");
  const meta = await api.meta().catch(() => ({ ingested_at: null, data_version: null }));

  // Item 1: same nav logic as before (no data/logic changes) - the header row itself is
  // replaced by the Dock + hub pages in item 2, this is purely a visual reskin for now.
  const navLinks = [
    ...domesticLeagues.map((l) => ({ href: `/leagues/${l.code}`, label: l.name })),
    ...(hasChampionsLeague ? [{ href: "/leagues/CL", label: "Champions League" }] : []),
    { href: "/leagues/international", label: "International" },
    { href: "/awards", label: "Awards" },
    { href: "/replay", label: "Replay" },
  ];

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      data-theme="dark"
    >
      <body className="relative flex min-h-full flex-col text-foreground">
        <SceneBackground />
        <header className="sticky top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-4">
          <nav className="glass mx-auto flex max-w-5xl items-center justify-between gap-4 !rounded-2xl px-4 py-3">
            <div className="flex items-center gap-6">
              <Link href="/" className="flex items-center gap-2 text-base font-bold tracking-tight text-foreground">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-sm text-accent-foreground shadow-[0_0_14px_var(--accent-glow)]">
                  K
                </span>
                KickCast
              </Link>
              <div className="hidden flex-wrap items-center gap-0.5 lg:flex">
                {navLinks.map((l) => (
                  <NavLink key={l.href} href={l.href}>
                    {l.label}
                  </NavLink>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="hidden items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs text-muted sm:flex">
                <SearchIcon className="h-3.5 w-3.5" />
                <input
                  type="search"
                  placeholder="Search teams, leagues..."
                  disabled
                  className="w-36 bg-transparent text-foreground outline-none placeholder:text-muted-2"
                  aria-label="Search (coming soon)"
                />
              </label>
              <MobileNav links={navLinks} />
            </div>
          </nav>
        </header>
        <main className="relative z-0 mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
        <footer className="relative z-0 px-4 pb-8 pt-4 text-center text-xs text-muted-2 sm:px-6">
          <div className="glass mx-auto max-w-3xl !rounded-2xl px-4 py-3">
            Data: openfootball (CC0), football-data.co.uk, StatsBomb Open Data, martj42/international_results (CC0),
            football-data.org (Champions League), API-Football (domestic scorer data), Wikipedia (CC BY-SA).
            Predictions are our own model, backtested out-of-sample - not a promise of accuracy.
            {meta.ingested_at && <> &middot; fixtures {timeAgo(meta.ingested_at)}</>}
          </div>
        </footer>
        <ChatWidget />
      </body>
    </html>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
      <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
