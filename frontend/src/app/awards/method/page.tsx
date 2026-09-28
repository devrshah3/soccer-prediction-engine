import Link from "next/link";
import { api, ApiError } from "@/lib/api";

export default async function AwardsMethodPage() {
  const backtest = await api.awardsMethod().catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });

  return (
    <div className="space-y-6">
      <div>
        <Link href="/awards" className="text-sm text-accent hover:underline">
          &larr; Awards
        </Link>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">Golden Boot projection: method</h1>
      </div>

      {!backtest ? (
        <div className="glass border-dashed p-8 text-center">
          <p className="text-sm text-muted">
            Backtest report not generated yet. Run{" "}
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
            <p className="mt-2 text-xs text-muted-2">{backtest.source}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="glass p-5 text-center">
              <p className="text-xs uppercase tracking-wide text-muted-2">Average error (goals)</p>
              <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                {backtest.summary.model_avg_mae_goals}
                <span className="ml-2 text-sm font-normal text-muted-2">
                  vs {backtest.summary.naive_avg_mae_goals} naive
                </span>
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
            has the lower average error on this test set ({backtest.n_test_points} matchday-cutoff tests across 4
            real historical seasons), though the two are close. The Awards page still uses the shrunken-rate
            model: unlike naive extrapolation, it stays well-defined and bounded when a player has played very few
            matches (e.g. matchday 1) rather than exploding from a single early goal &mdash; a structural reason,
            not something this backtest (which only tests matchday 5/10/20 cutoffs) directly measured.
          </div>

          <div className="overflow-x-auto glass">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wide text-muted-2">
                <tr>
                  <th className="px-4 py-3 font-medium">League</th>
                  <th className="px-2 py-3 text-right font-medium">Cutoff</th>
                  <th className="px-2 py-3 text-right font-medium">Model MAE</th>
                  <th className="px-2 py-3 text-right font-medium">Naive MAE</th>
                  <th className="px-3 py-3 font-medium">Actual top scorer</th>
                  <th className="px-3 py-3 font-medium">Model picked</th>
                </tr>
              </thead>
              <tbody>
                {backtest.results.map((r) => (
                  <tr key={`${r.league}-${r.cutoff_matchday}`} className="border-t border-white/10">
                    <td className="px-4 py-2.5 text-foreground">{r.league}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">MD{r.cutoff_matchday}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{r.model_mae}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{r.naive_mae}</td>
                    <td className="px-3 py-2.5 text-muted">{r.actual_top_scorer}</td>
                    <td className={`px-3 py-2.5 ${r.model_hit ? "text-accent" : "text-muted"}`}>
                      {r.model_picked} {r.model_hit && "✓"}
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
