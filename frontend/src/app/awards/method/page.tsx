import Link from "next/link";
import { api, ApiError } from "@/lib/api";

// Fetches live data from the backend on every request - never statically prerendered, since
// the backend isn't guaranteed reachable at frontend build time (separate deploys).
export const dynamic = "force-dynamic";

export default async function AwardsMethodPage() {
  const backtest = await api.awardsMethod().catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });

  return (
    <div className="space-y-6">
      <div>
        <Link href="/awards" className="text-sm text-accent-text hover:underline">
          &larr; Awards
        </Link>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">Golden Boot projection: method</h1>
      </div>

      {!backtest ? (
        <div className="glass border-dashed p-8 text-center">
          <p className="text-sm text-muted">
            The test report hasn&apos;t been generated yet. Run{" "}
            <code className="rounded bg-white/10 px-1.5 py-0.5 text-muted-2">
              python scripts/backtest_golden_boot_projection.py
            </code>
            .
          </p>
        </div>
      ) : (
        <>
          <div className="glass p-5">
            <p className="text-sm text-muted">{backtest.method}</p>
            <p className="mt-2 text-xs text-muted-2">{backtest.data_note}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="glass p-5 text-center">
              <p className="text-xs uppercase tracking-wide text-muted-2">Average error (goals)</p>
              <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                {backtest.summary.model_avg_mae_goals}
                <span className="ml-2 text-sm font-normal text-muted-2">vs {backtest.summary.naive_avg_mae_goals} naive</span>
              </p>
            </div>
            <div className="glass p-5 text-center">
              <p className="text-xs uppercase tracking-wide text-muted-2">Hit rate (picked the real top scorer)</p>
              <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                {Math.round(backtest.summary.model_hit_rate * 100)}%
                <span className="ml-2 text-sm font-normal text-muted-2">
                  vs {Math.round(backtest.summary.naive_hit_rate * 100)}% naive
                </span>
              </p>
            </div>
          </div>

          <div className="glass border-dashed p-4 text-center text-sm text-muted">
            Honest result: the{" "}
            <span className="font-medium text-foreground">
              {backtest.summary.winner === "model" ? "shrunken-rate model" : "naive current-pace baseline"}
            </span>{" "}
            has the lower average error across all {backtest.n_test_points} tests, though the two are close. The
            Awards page still uses the shrunken-rate model: unlike naive extrapolation, it stays well-defined and
            bounded when a player has played very few matches (e.g. matchday 1) rather than exploding from a single
            early goal &mdash; a structural reason, not something this test (which only used matchday 5, 10 and 20
            cutoffs) directly measured.
          </div>

          <div className="overflow-x-auto glass">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wide text-muted-2">
                <tr>
                  <th className="px-4 py-3 font-medium">Projected at</th>
                  <th className="px-2 py-3 text-right font-medium">Tests</th>
                  <th className="px-2 py-3 text-right font-medium">Model error</th>
                  <th className="px-2 py-3 text-right font-medium">Naive error</th>
                  <th className="px-2 py-3 text-right font-medium">Model hits</th>
                  <th className="px-4 py-3 text-right font-medium">Naive hits</th>
                </tr>
              </thead>
              <tbody>
                {backtest.by_cutoff.map((r) => (
                  <tr key={r.cutoff_matchday} className="border-t border-white/10">
                    <td className="px-4 py-2.5 text-foreground">Matchday {r.cutoff_matchday}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{r.tests}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{r.model_avg_mae}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{r.naive_avg_mae}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">
                      {r.model_hits}/{r.tests}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-muted">
                      {r.naive_hits}/{r.tests}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
