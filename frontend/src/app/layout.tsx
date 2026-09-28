import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { ChatWidget } from "@/components/ChatWidget";
import { NavPill } from "@/components/glass/NavPill";
import { SearchBox } from "@/components/SearchBox";
import { SceneBackground } from "@/components/SceneBackground";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const DESCRIPTION = "Free soccer scores, fixtures, and our own match predictions.";

export const metadata: Metadata = {
  title: { default: "Soccer Prediction Engine", template: "%s \u00b7 Soccer Prediction Engine" },
  description: DESCRIPTION,
  applicationName: "Soccer Prediction Engine",
  openGraph: {
    type: "website",
    siteName: "Soccer Prediction Engine",
    title: "Soccer Prediction Engine",
    description: DESCRIPTION,
  },
  twitter: { card: "summary", title: "Soccer Prediction Engine", description: DESCRIPTION },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
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
              aria-label="Soccer Prediction Engine home"
              className="glass glass-float pointer-events-auto flex w-fit items-center gap-2 !rounded-full p-1 text-base font-bold tracking-tight text-foreground min-[1100px]:pr-4"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-[13px] tracking-tight text-accent-foreground shadow-[0_0_14px_var(--accent-glow)]">
                SP
              </span>
              {/* The full name is long: only from 1100px up, so it can never crowd the pill or search. */}
              <span className="hidden whitespace-nowrap min-[1100px]:inline">Soccer Prediction Engine</span>
            </Link>
            <div className="flex justify-center">
              <NavPill />
            </div>
            <SearchBox />
          </nav>
        </header>
        <main className="relative z-0 mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
        {/* One plain, quiet link - no box or glass. Bottom padding clears the assistant bubble
            (bottom-right, ~76px tall from the edge) so it never covers the last cards or this link. */}
        <footer className="relative z-0 px-4 pb-28 pt-8 text-center">
          <Link href="/about" className="text-[11px] text-muted-2/70 underline-offset-2 hover:text-muted hover:underline">
            Data sources &amp; credits
          </Link>
        </footer>
        <ChatWidget />
      </body>
    </html>
  );
}
