import { api } from "@/lib/api";

export default async function AwardsPage() {
  const awards = await api.awards();

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-zinc-50">Awards</h1>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-zinc-200">Golden Boot</h2>
        <p className="mb-3 text-sm text-zinc-500">{awards.golden_boot.reason}</p>
        {awards.golden_boot.international_top_scorers.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-zinc-400">
              International top scorers (last {awards.golden_boot.lookback_days} days)
            </h3>
            <ol className="space-y-1 text-sm text-zinc-300">
              {awards.golden_boot.international_top_scorers.map((s, i) => (
                <li key={`${s.player}-${s.team_id}`} className="flex justify-between border-b border-zinc-800 py-1">
                  <span>
                    {i + 1}. {s.player} <span className="text-zinc-500">({s.team_name})</span>
                  </span>
                  <span className="font-semibold">{s.goals}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-zinc-200">Ballon d&apos;Or / The Best</h2>
        <p className="text-sm text-zinc-500">{awards.ballon_dor.reason}</p>
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-zinc-200">Puskás Award</h2>
        <p className="text-sm text-zinc-500">{awards.puskas.reason}</p>
      </section>
    </div>
  );
}
