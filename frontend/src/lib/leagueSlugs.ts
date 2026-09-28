// Central code<->slug map for the 7 real competitions in the DB (see `SELECT code FROM
// leagues` / GET /leagues - there is no separate "Nations League" code; those matches are
// part of the single "international" bucket alongside friendlies and qualifiers, so it
// keeps the display name "International" rather than inventing a competition our data
// doesn't actually separate out). Item 4 reuses this for display names shown elsewhere.
export const CODE_TO_SLUG: Record<string, string> = {
  "en.1": "premier-league",
  "es.1": "la-liga",
  "it.1": "serie-a",
  "de.1": "bundesliga",
  "fr.1": "ligue-1",
  CL: "champions-league",
  international: "international",
};

export const SLUG_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(CODE_TO_SLUG).map(([code, slug]) => [slug, code])
);

export function slugForCode(code: string): string {
  return CODE_TO_SLUG[code] ?? code;
}

// Item 4: a raw code (e.g. "en.1") must never reach a rendered page - this is the
// fallback for the handful of call sites that only have the code, not a fetched League
// object (api.leagues() already returns the real name and is preferred wherever it's
// already in hand, e.g. the leagues hub).
const CODE_TO_NAME: Record<string, string> = {
  "en.1": "Premier League",
  "es.1": "La Liga",
  "it.1": "Serie A",
  "de.1": "Bundesliga",
  "fr.1": "Ligue 1",
  CL: "UEFA Champions League",
  international: "International",
};

export function nameForCode(code: string): string {
  return CODE_TO_NAME[code] ?? code;
}
