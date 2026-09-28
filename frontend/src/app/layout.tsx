import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ChatWidget } from "@/components/ChatWidget";
import { MobileNav } from "@/components/MobileNav";
import { NavLink } from "@/components/NavLink";
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
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
          <nav className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
            <div className="flex items-center gap-6">
              <Link href="/" className="flex items-center gap-2 text-base font-bold tracking-tight text-foreground">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-hover text-sm text-accent-foreground shadow-sm shadow-accent/40">
                  K
                </span>
                KickCast
              </Link>
              <div className="hidden flex-wrap items-center gap-0.5 sm:flex">
                {navLinks.map((l) => (
                  <NavLink key={l.href} href={l.href}>
                    {l.label}
                  </NavLink>
                ))}
              </div>
            </div>
            <MobileNav links={navLinks} />
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
        <footer className="border-t border-border px-4 py-6 text-center text-xs text-muted-2 sm:px-6">
          Data: openfootball (CC0), football-data.co.uk, StatsBomb Open Data, martj42/international_results (CC0),
          football-data.org (Champions League), API-Football (domestic scorer data), Wikipedia (CC BY-SA).
          Predictions are our own model, backtested out-of-sample - not a promise of accuracy.
          {meta.ingested_at && <> &middot; fixtures {timeAgo(meta.ingested_at)}</>}
        </footer>
        <ChatWidget />
      </body>
    </html>
  );
}
