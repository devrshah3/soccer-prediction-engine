import Link from "next/link";

const SOURCES: { name: string; used: string; license: string; href?: string }[] = [
  {
    name: "openfootball",
    used: "Domestic league fixtures and results.",
    license: "CC0 (public domain)",
    href: "https://github.com/openfootball",
  },
  {
    name: "football-data.co.uk",
    used: "Historical results and match statistics (e.g. card counts) used to fit our models.",
    license: "Free for personal/non-commercial use, with credit",
    href: "https://www.football-data.co.uk",
  },
  {
    name: "martj42/international_results",
    used: "International results and goalscorers.",
    license: "CC0 (public domain)",
    href: "https://github.com/martj42/international_results",
  },
  {
    name: "football-data.org",
    used: "Champions League fixtures and results, and live current-season top-scorer tables (free tier).",
    license: "Free tier, attribution required",
    href: "https://www.football-data.org",
  },
  {
    name: "API-Football",
    used: "Past-season domestic top-scorer tallies (free tier).",
    license: "Free tier terms",
    href: "https://www.api-football.com",
  },
  {
    name: "UEFA.com",
    used: "The published Nations League fixture list.",
    license: "Facts only (dates, teams, venues); no logos or text reused",
    href: "https://www.uefa.com",
  },
  {
    name: "StatsBomb Open Data",
    used: "Historical match-event data used only behind the scenes: goal-timing and corner rates, and testing the Golden Boot projection. Never shown as live data.",
    license: "StatsBomb Open Data licence — credit StatsBomb as the data source",
    href: "https://github.com/statsbomb/open-data",
  },
  {
    name: "Wikipedia",
    used: "Background text the assistant quotes for facts outside our database, always cited.",
    license: "CC BY-SA",
    href: "https://www.wikipedia.org",
  },
  {
    name: "Google Gemini and YouTube Data API",
    used: "The assistant's phrasing (only from facts we looked up ourselves) and official highlight links.",
    license: "Google API terms",
  },
];

export default function AboutPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Data sources &amp; credits</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Everything on Soccer Prediction Engine comes from the free sources below. Predictions are our own model, backtested
          out-of-sample &mdash; not a promise of accuracy. We don&apos;t use any club, league or federation logos or
          crests.
        </p>
        <Link href="/awards/method" className="mt-2 inline-block text-sm text-accent-text hover:underline">
          How the Golden Boot projection was tested &rarr;
        </Link>
      </div>
      <ul className="grid gap-3.5 sm:grid-cols-2">
        {SOURCES.map((s) => (
          <li key={s.name} className="glass p-4">
            <h2 className="text-sm font-semibold text-foreground">
              {s.href ? (
                <a href={s.href} target="_blank" rel="noreferrer" className="hover:text-accent-text">
                  {s.name}
                </a>
              ) : (
                s.name
              )}
            </h2>
            <p className="mt-1.5 text-sm text-muted">{s.used}</p>
            <p className="mt-2 text-xs text-muted-2">{s.license}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
