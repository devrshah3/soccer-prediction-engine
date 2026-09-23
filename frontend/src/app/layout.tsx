import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { api } from "@/lib/api";
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
  let leagues: { code: string; name: string }[] = [];
  try {
    leagues = (await api.leagues()).filter((l) => l.kind === "domestic_league");
  } catch {
    // backend not reachable (e.g. during a frontend-only lint/build check) - nav degrades gracefully
  }

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      data-theme="dark"
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <header className="border-b border-zinc-800">
          <nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-4">
            <Link href="/" className="text-lg font-bold tracking-tight text-emerald-400">
              KickCast
            </Link>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-400">
              {leagues.map((l) => (
                <Link key={l.code} href={`/leagues/${l.code}`} className="hover:text-emerald-400">
                  {l.name}
                </Link>
              ))}
              <Link href="/leagues/international" className="hover:text-emerald-400">
                International
              </Link>
              <Link href="/assistant" className="hover:text-emerald-400">
                Ask about soccer
              </Link>
              <Link href="/awards" className="hover:text-emerald-400">
                Awards
              </Link>
              <Link href="/replay" className="hover:text-emerald-400">
                Replay
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t border-zinc-800 px-4 py-6 text-center text-xs text-zinc-600">
          Data: openfootball (CC0), football-data.co.uk, StatsBomb Open Data, martj42/international_results (CC0).
          Predictions are our own model, backtested out-of-sample - not a promise of accuracy.
        </footer>
      </body>
    </html>
  );
}
