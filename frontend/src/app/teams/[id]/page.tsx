import Link from "next/link";
import { notFound } from "next/navigation";
import { FormDots } from "@/components/FormDots";
import { KickoffTime } from "@/components/KickoffTime";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { Tabs } from "@/components/Tabs";
import { TeamCrest } from "@/components/TeamCrest";
import { api, ApiError } from "@/lib/api";
import { nameForCode, slugForCode } from "@/lib/leagueSlugs";

export default async function TeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = await params;
  // Next.js 16's dynamic segments are not guaranteed pre-decoded (differs from earlier
  // versions - see frontend/AGENTS.md); decodeURIComponent is a safe no-op if it already was.
  const id = decodeURIComponent(rawId);

  const team = await api.team(id).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
  if (!team) notFound();

  const [upcoming, recent, nextPrediction, trophyOdds] = await Promise.all([
    api.teamFixtures(id, "scheduled", 20),
    api.teamFixtures(id, "finished", 10),
    team.next_match ? api.prediction(team.next_match.id) : Promise.resolve(null),
    team.league_code ? api.trophyOdds(team.league_code, team.season ?? undefined) : Promise.resolve(null),
  ]);
  const teamOdds = trophyOdds?.teams.find((t) => t.team_id === id);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start gap-4">
        <TeamCrest name={team.name} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{team.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {team.country ?? "International"}
            {team.league_code && (
              <>
                {" "}
                &middot;{" "}
                <Link href={`/leagues/${slugForCode(team.league_code)}`} className="hover:text-accent-text">
                  {nameForCode(team.league_code)}
                </Link>
                {team.position && ` — ${team.position}${ordinal(team.position)} (${team.season})`}
              </>
            )}
          </p>
          <div className="mt-3">
            <FormDots form={team.form} />
          </div>
        </div>
        {teamOdds && (
          <div className="glass glass-float flex gap-4 px-4 py-3 text-center">
            <MiniStat label="Title" value={teamOdds.title_pct} />
            <MiniStat label="Top 4" value={teamOdds.top4_pct} />
            <MiniStat label="Releg." value={teamOdds.relegation_pct} tone="danger" />
          </div>
        )}
      </div>

      {team.next_match && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-foreground">Next match</h2>
          <div className="glass p-5">
            <p className="mb-3 text-sm text-muted">
              {team.next_match.round} &middot;{" "}
              <KickoffTime date={team.next_match.date} kickoff={team.next_match.kickoff} />
            </p>
            <p className="mb-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 text-center text-base font-medium text-foreground">
              <span className="flex items-center gap-2">
                <TeamCrest name={team.next_match.home_team.name} /> {team.next_match.home_team.name}
              </span>
              <span className="shrink-0 text-sm text-muted-2">vs</span>
              <span className="flex items-center gap-2">
                {team.next_match.away_team.name} <TeamCrest name={team.next_match.away_team.name} />
              </span>
            </p>
            {nextPrediction ? (
              <>
                <ProbabilityBar
                  size="lg"
                  home={nextPrediction.probabilities.home}
                  draw={nextPrediction.probabilities.draw}
                  away={nextPrediction.probabilities.away}
                  homeLabel={team.next_match.home_team.name}
                  awayLabel={team.next_match.away_team.name}
                />
                <p className="mt-3 text-xs text-muted-2">
                  as of {nextPrediction.as_of} &middot; evidence {nextPrediction.evidence} &middot;{" "}
                  expected goals {nextPrediction.expected_goals.home.toFixed(2)} -{" "}
                  {nextPrediction.expected_goals.away.toFixed(2)}
                </p>
              </>
            ) : (
              <p className="text-xs text-muted-2">prediction not available yet</p>
            )}
            <Link
              href={`/matches/${team.next_match.id}`}
              className="mt-4 inline-block text-sm font-medium text-accent-text hover:underline"
            >
              Full match page &rarr;
            </Link>
          </div>
        </section>
      )}

      <Tabs
        tabs={[
          {
            label: "Upcoming",
            content:
              upcoming.length === 0 ? (
                <p className="text-sm text-muted-2">No scheduled fixtures found.</p>
              ) : (
                <ul className="divide-y divide-border glass">
                  {upcoming.map((m) => (
                    <li key={m.id}>
                      <Link
                        href={`/matches/${m.id}`}
                        className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-surface-hover"
                      >
                        <span className="truncate text-foreground">
                          {m.home_team.name} vs {m.away_team.name}
                        </span>
                        <span className="shrink-0 text-muted-2">
                          <KickoffTime date={m.date} kickoff={m.kickoff} />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ),
          },
          {
            label: "Results",
            content:
              recent.length === 0 ? (
                <p className="text-sm text-muted-2">No finished matches found.</p>
              ) : (
                <ul className="divide-y divide-border glass">
                  {recent.map((m) => (
                    <li key={m.id}>
                      <Link
                        href={`/matches/${m.id}`}
                        className="flex items-center justify-between gap-3 px-4 py-3 text-sm transition-colors hover:bg-surface-hover"
                      >
                        <span className="truncate text-foreground">
                          {m.home_team.name} {m.home_goals} &ndash; {m.away_goals} {m.away_team.name}
                        </span>
                        <span className="shrink-0 text-muted-2">{m.date}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ),
          },
          ...(teamOdds
            ? [
                {
                  label: "Trophy odds",
                  content: (
                    <div className="grid grid-cols-3 gap-3 glass p-5 text-center sm:w-80">
                      <MiniStat label="Title" value={teamOdds.title_pct} big />
                      <MiniStat label="Top 4" value={teamOdds.top4_pct} big />
                      <MiniStat label="Relegation" value={teamOdds.relegation_pct} tone="danger" big />
                      <div className="col-span-3 mt-2 border-t border-border pt-3 text-xs text-muted-2">
                        Expected finish {teamOdds.expected_position.toFixed(1)} &middot; expected points{" "}
                        {teamOdds.expected_points.toFixed(1)}
                      </div>
                    </div>
                  ),
                },
              ]
            : []),
        ]}
      />
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone,
  big,
}: {
  label: string;
  value: number;
  tone?: "danger";
  big?: boolean;
}) {
  return (
    <div>
      <p className={`${big ? "text-xl" : "text-sm"} font-bold tabular-nums ${tone === "danger" ? "text-danger-text" : "text-accent-text"}`}>
        {(value * 100).toFixed(1)}%
      </p>
      <p className="text-[10px] uppercase tracking-wide text-muted-2">{label}</p>
    </div>
  );
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return s[(v - 20) % 10] || s[v] || s[0];
}
