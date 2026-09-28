import Link from "next/link";
import { ReplayMatchCard } from "@/components/ReplayMatchCard";
import { ReplayTimezone } from "@/components/ReplayTimezone";
import { api, ApiError } from "@/lib/api";
import { formatShortDate } from "@/lib/time";

// Item 6: Replay is yesterday - the viewer's LOCAL yesterday, worked out at request time by
// the API from the real clock plus the offset the browser reports (?tz=). `date` exists only
// for the "most recent day that had matches" link and can never be today or later.
export default async function ReplayPage({ searchParams }: { searchParams: Promise<{ tz?: string; date?: string }> }) {
  const { tz, date } = await searchParams;
  if (tz === undefined) {
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Replay</h1>
        <ReplayTimezone date={date} />
      </div>
    );
  }

  const offset = Number.parseInt(tz, 10);
  const safeOffset = Number.isFinite(offset) ? offset : 0;
  const day = await api.replayDay(safeOffset, date).catch((e) => {
    if (e instanceof ApiError && e.status === 400) return null;
    throw e;
  });
  if (!day) {
    return (
      <div className="glass border-dashed p-8 text-center">
        <p className="text-sm text-muted">Replay only covers days before today.</p>
        <Link href={`/replay?tz=${safeOffset}`} className="mt-2 inline-block text-sm text-accent-text hover:underline">
          Go to yesterday &rarr;
        </Link>
      </div>
    );
  }

  const isYesterday = date === undefined;
  const link = (d: string) => `/replay?tz=${safeOffset}&date=${d}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Replay</h1>
        <p className="mt-1 text-sm text-muted">
          {isYesterday ? "Yesterday" : "Earlier day"} &middot; {formatShortDate(day.date)}
          {!isYesterday && (
            <>
              {" "}
              &middot;{" "}
              <Link href={`/replay?tz=${safeOffset}`} className="text-accent-text hover:underline">
                Back to yesterday
              </Link>
            </>
          )}
        </p>
      </div>

      {day.matches.length === 0 ? (
        <div className="glass border-dashed p-8 text-center">
          <p className="text-sm text-muted">
            No matches were played {isYesterday ? "yesterday" : "on this day"} ({formatShortDate(day.date)}).
          </p>
          {day.most_recent_day_with_matches && (
            <Link href={link(day.most_recent_day_with_matches)} className="mt-2 inline-block text-sm text-accent-text hover:underline">
              See {formatShortDate(day.most_recent_day_with_matches)}, the most recent day with matches &rarr;
            </Link>
          )}
        </div>
      ) : (
        <>
          {day.most_recent_day_with_results && (
            <div className="glass border-dashed p-4 text-sm text-muted">
              None of these matches have a recorded result yet.{" "}
              <Link href={link(day.most_recent_day_with_results)} className="text-accent-text hover:underline">
                See {formatShortDate(day.most_recent_day_with_results)}, the most recent day with results &rarr;
              </Link>
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {day.matches.map((m) => (
              <ReplayMatchCard key={m.id} match={m} noEventsNote={day.no_events_note} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
