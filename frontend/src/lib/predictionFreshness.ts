// D.11: a visible "Prediction may be outdated" warning only when it's actually
// justified - the prediction is for a match happening soon (within 7 days) AND it hasn't
// been recomputed in the last 48 hours. Otherwise a card shows nothing about staleness at
// all, per the brief ("only show a visible warning... otherwise show nothing").
export function isPredictionStale(computedAt: string | null, matchDate: string, now: Date = new Date()): boolean {
  if (!computedAt) return false; // no computed_at to judge staleness from - don't guess
  const daysUntilMatch = (new Date(`${matchDate}T00:00:00Z`).getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  if (daysUntilMatch > 7) return false;
  const hoursSinceComputed = (now.getTime() - new Date(computedAt).getTime()) / (1000 * 60 * 60);
  return hoursSinceComputed > 48;
}
