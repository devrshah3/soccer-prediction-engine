"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Matches", icon: MatchesIcon },
  { href: "/leagues", label: "Leagues", icon: LeaguesIcon },
  { href: "/awards", label: "Awards", icon: AwardsIcon },
  { href: "/replay", label: "Replay", icon: ReplayIcon },
];

// Floating bottom glass dock (item 2's four sections). The active item is a brighter
// glass "lens" with its label; others are icon-only with an aria-label. Fixed, so it must
// never overlap the assistant bubble (bottom-right) - the dock is centered and the
// assistant bubble sits further right/lower, verified in the Playwright screenshots.
export function Dock() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="glass fixed inset-x-0 bottom-4 z-40 mx-auto flex w-fit items-center gap-1 !rounded-full p-1.5 sm:bottom-6"
    >
      {ITEMS.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-2 rounded-full px-3 py-2.5 text-xs font-medium transition-all sm:px-4 ${
              active
                ? "bg-gradient-to-r from-accent to-accent-2 text-accent-foreground shadow-[0_0_18px_var(--accent-glow)]"
                : "text-muted hover:bg-white/[0.08] hover:text-foreground"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {active && <span className="hidden sm:inline">{item.label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

function MatchesIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="3" y="4" width="18" height="17" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 9h18M8 2v4M16 2v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function LeaguesIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M8 21h8M12 17v4M6 4h12v4a6 6 0 0 1-12 0V4Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M6 6H3v1a4 4 0 0 0 4 4M18 6h3v1a4 4 0 0 1-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
function AwardsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="9" r="6" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 14.5 7 22l5-3 5 3-1.5-7.5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
function ReplayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 3-6.7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M3 4v5h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
