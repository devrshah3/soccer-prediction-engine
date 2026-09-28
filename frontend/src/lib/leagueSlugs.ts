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
