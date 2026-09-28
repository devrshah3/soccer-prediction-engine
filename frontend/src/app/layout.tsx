import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ChatWidget } from "@/components/ChatWidget";
import { NavPill } from "@/components/glass/NavPill";
import { SearchBox } from "@/components/SearchBox";
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
      className={`${geistSans.variable} ${geistMono.variable} h-full scroll-pt-24 antialiased`}
      data-theme="dark"
    >
      <body className="relative flex min-h-full flex-col text-foreground">
        <SceneBackground />
        <header className="pointer-events-none sticky top-3 z-40 px-3 sm:px-6">
          <nav
            aria-label="Site"
            className="relative mx-auto grid max-w-5xl grid-cols-[auto_1fr_auto] items-center gap-2 sm:grid-cols-[1fr_auto_1fr] sm:gap-4"
          >
            <Link
              href="/"
              aria-label="KickCast home"
              className="glass glass-float pointer-events-auto flex w-fit items-center gap-2 !rounded-full p-1 text-base font-bold tracking-tight text-foreground sm:pr-4"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-sm text-accent-foreground shadow-[0_0_14px_var(--accent-glow)]">
                K
              </span>
              <span className="hidden sm:inline">KickCast</span>
            </Link>
            <div className="flex justify-center">
              <NavPill />
            </div>
            <SearchBox />
          </nav>
        </header>
        <main className="relative z-0 mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
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
