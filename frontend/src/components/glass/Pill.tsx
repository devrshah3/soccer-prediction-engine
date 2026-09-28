import type { ReactNode } from "react";

export function Pill({
  children,
  active = false,
  onClick,
  className = "",
  as: Component = "button",
  ...rest
}: {
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  className?: string;
  as?: "button" | "span";
  [key: string]: unknown;
}) {
  const base =
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors";
  const tone = active
    ? "border-accent/50 bg-accent-soft text-accent-text"
    : "border-white/15 bg-white/[0.06] text-muted hover:text-foreground hover:bg-white/[0.1]";
  if (Component === "span") {
    return (
      <span className={`${base} ${tone} ${className}`} {...rest}>
        {children}
      </span>
    );
  }
  return (
    <button onClick={onClick} className={`${base} ${tone} ${className}`} {...rest}>
      {children}
    </button>
  );
}
