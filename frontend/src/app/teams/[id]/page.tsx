import Link from "next/link";
import { notFound } from "next/navigation";
import { FormDots } from "@/components/FormDots";
import { KickoffTime } from "@/components/KickoffTime";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { api, ApiError } from "@/lib/api";

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

  const [upcoming, recent, nextPrediction] = await Promise.all([
    api.teamFixtures(id, "scheduled", 20),
    api.teamFixtures(id, "finished", 10),
    team.next_match ? api.prediction(team.next_match.id) : Promise.resolve(null),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-50">{team.name}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {team.country ?? "International"}
          {team.league_code && (
            <>
              {" "}
              &middot;{" "}
              <Link href={`/leagues/${team.league_code}`} className="hover:text-emerald-400">
                {team.league_code}
              </Link>
              {team.position && ` - ${team.position}${ordinal(team.position)} (${team.season})`}
            </>
          )}
        </p>
        <div className="mt-2">
          <FormDots form={team.form} />
        </div>
      </div>

      {team.next_match && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-zinc-200">Next match</h2>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <p className="mb-2 text-sm text-zinc-400">
              {team.next_match.round} &middot;{" "}
              <KickoffTime date={team.next_match.date} kickoff={team.next_match.kickoff} />
            </p>
            <p className="mb-3 text-base font-medium text-zinc-100">
              {team.next_match.home_team.name} vs {team.next_match.away_team.name}
            </p>
            {nextPrediction ? (
              <>
                <ProbabilityBar
                  home={nextPrediction.probabilities.home}
                  draw={nextPrediction.probabilities.draw}
                  away={nextPrediction.probabilities.away}
                  homeLabel={team.next_match.home_team.name}
                  awayLabel={team.next_match.away_team.name}
                />
                <p className="mt-2 text-xs text-zinc-500">
                  as of {nextPrediction.as_of} &middot; evidence {nextPrediction.evidence} &middot;{" "}
                  expected goals {nextPrediction.expected_goals.home.toFixed(2)} -{" "}
                  {nextPrediction.expected_goals.away.toFixed(2)}
                </p>
              </>
            ) : (
              <p className="text-xs text-zinc-500">prediction not available yet</p>
            )}
            <Link
              href={`/matches/${team.next_match.id}`}
              className="mt-3 inline-block text-sm text-emerald-400 hover:underline"
            >
              Full match page &rarr;
            </Link>
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold text-zinc-200">Upcoming schedule</h2>
        {upcoming.length === 0 ? (
          <p className="text-sm text-zinc-500">No scheduled fixtures found.</p>
        ) : (
          <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
            {upcoming.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-4 py-2 text-sm">
                <Link href={`/matches/${m.id}`} className="hover:text-emerald-400">
                  {m.home_team.name} vs {m.away_team.name}
                </Link>
                <span className="text-zinc-500">
                  <KickoffTime date={m.date} kickoff={m.kickoff} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-zinc-200">Recent results</h2>
        {recent.length === 0 ? (
          <p className="text-sm text-zinc-500">No finished matches found.</p>
        ) : (
          <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
            {recent.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-4 py-2 text-sm">
                <Link href={`/matches/${m.id}`} className="hover:text-emerald-400">
                  {m.home_team.name} {m.home_goals} - {m.away_goals} {m.away_team.name}
                </Link>
                <span className="text-zinc-500">{m.date}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return s[(v - 20) % 10] || s[v] || s[0];
}
