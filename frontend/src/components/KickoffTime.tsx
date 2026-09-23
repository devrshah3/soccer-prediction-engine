"use client";

// Renders kickoff in the viewer's local time zone. ASSUMPTION (unverified against the
// source docs - flagged in MORNING_REPORT.md): stored `kickoff` strings are treated as UTC.
// If that assumption is wrong the displayed time will be off by a fixed offset; the raw
// source value is always shown alongside it so nothing is hidden.
export function KickoffTime({ date, kickoff }: { date: string; kickoff: string | null }) {
  if (!kickoff) {
    return <span>{date}</span>;
  }
  const iso = `${date}T${kickoff.length === 5 ? kickoff : kickoff.padStart(5, "0")}:00Z`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return (
      <span>
        {date} &middot; {kickoff}
      </span>
    );
  }
  const local = d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <span title={`source-reported kickoff: ${date} ${kickoff}`}>{local}</span>
  );
}
