import type { ReactNode } from "react";

// Same glass recipe as GlassCard, sized/spaced for a page-level section rather than a
// list item.
export function GlassPanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`glass p-5 sm:p-6 ${className}`}>{children}</section>;
}
