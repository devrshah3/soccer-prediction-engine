"use client";

// Renders kickoff in the viewer's local time zone. `kickoff` is stored as real UTC
// (converted DST-aware from each league's local kickoff time at ingestion - see
// kickcast_engine/data/kickoff.py, verified against a real fixture: Arsenal vs Coventry
// City, 2026-08-21, 20:00 in London (BST, UTC+1) -> stored/served as "19:00" UTC). The
// raw source value is still shown alongside it so nothing is hidden if this ever drifts.
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
