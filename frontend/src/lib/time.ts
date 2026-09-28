// Computed at request time on the server (pages fetch with cache: "no-store"), so this
// never needs client-side rehydration/ticking to stay accurate for a page view.
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `updated ${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `updated ${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `updated ${diffDay}d ago`;
}

// "2026-10-10" -> "Oct 10", for the homepage's "club football resumes <date>" note.
export function formatShortDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}
