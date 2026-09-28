import Link from "next/link";
import type { ReactNode } from "react";

// The base glass container - see .glass in globals.css for the exact recipe (gradient
// fill, blur+saturate backdrop-filter with a solid fallback, border, inset highlight,
// shadow, specular sheen). Used for cards and small containers; GlassPanel is the same
// recipe for a larger section. Never used per-row inside a long list (see .glass-row).
export function GlassCard({
  children,
  className = "",
  href,
  as: Component = "div",
}: {
  children: ReactNode;
  className?: string;
  href?: string;
  as?: "div" | "section";
}) {
  const classes = `glass p-4 transition-transform ${className}`;
  if (href) {
    return (
      <Link href={href} className={`${classes} block hover:-translate-y-0.5`}>
        {children}
      </Link>
    );
  }
  return <Component className={classes}>{children}</Component>;
}
