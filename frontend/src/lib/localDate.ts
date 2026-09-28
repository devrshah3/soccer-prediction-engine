import type { Match } from "./api";

// B.6: a match's stored `date` is its UTC calendar date (kickoff.py converts every
// source's local kickoff to UTC at ingest time) - which is NOT always the viewer's local
// calendar date. A 9pm US Eastern kickoff is 01:00/02:00 UTC the NEXT day, so it's stored
// under tomorrow's UTC date; a US viewer watching it start would still call that "today".
// This computes which local calendar date a match actually falls on for a viewer at a
// given UTC offset (minutes east of UTC, i.e. what Date.getTimezoneOffset() returns
// negated), so the frontend can re-bucket a fetched day's matches instead of trusting the
// UTC date verbatim.
export function localCalendarDate(match: Pick<Match, "date" | "kickoff">, offsetMinutes: number): string {
  if (!match.kickoff) return match.date;
  const utcMs = new Date(`${match.date}T${match.kickoff}:00Z`).getTime();
  if (Number.isNaN(utcMs)) return match.date;
  const localMs = utcMs + offsetMinutes * 60000;
  return new Date(localMs).toISOString().slice(0, 10);
}
