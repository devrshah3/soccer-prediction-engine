import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ChatWidget } from "@/components/ChatWidget";
import { Dock } from "@/components/glass/Dock";
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
  const meta = await api.meta().catch(() => ({ ingested_at: null, data_version: null }));

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
            <Link href="/" className="flex items-center gap-2 text-base font-bold tracking-tight text-foreground">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-sm text-accent-foreground shadow-[0_0_14px_var(--accent-glow)]">
                K
              </span>
              KickCast
            </Link>
            <label className="flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs text-muted">
              <SearchIcon className="h-3.5 w-3.5 shrink-0" />
              <input
                type="search"
                placeholder="Search teams, leagues..."
                disabled
                className="w-24 bg-transparent text-foreground outline-none placeholder:text-muted-2 sm:w-36"
                aria-label="Search (coming soon)"
              />
            </label>
          </nav>
        </header>
        <main className="relative z-0 mx-auto w-full max-w-5xl flex-1 px-4 py-6 pb-28 sm:px-6 sm:py-8 sm:pb-28">{children}</main>
        <Dock />
        <footer className="relative z-0 px-4 pb-8 pt-4 text-center text-xs text-muted-2 sm:px-6">
          <div className="glass mx-auto max-w-3xl !rounded-2xl px-4 py-3">
            Predictions are our own model, backtested out-of-sample - not a promise of accuracy.
            {meta.ingested_at && <> &middot; fixtures {timeAgo(meta.ingested_at)}</>}
            {" "}&middot;{" "}
            <Link href="/about" className="text-accent hover:underline">
              Data sources &amp; credits
            </Link>
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
