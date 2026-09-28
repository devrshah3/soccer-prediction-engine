import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

// Item 6: StatsBomb and the historical 2015/16 seasons are only ever credited on the Data
// sources page - nothing else user-facing may name them (the backtest that uses that data is
// reported as aggregate results only).
describe("user-facing copy", () => {
  it("names StatsBomb / 2015-16 nowhere except the Data sources page", () => {
    const offenders = sourceFiles(join(process.cwd(), "src"))
      .filter((f) => !f.endsWith(join("app", "about", "page.tsx")))
      .filter((f) => /statsbomb|2015[/-]16/i.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });

  it("still credits StatsBomb on the Data sources page (its licence requires it)", () => {
    const about = readFileSync(join(process.cwd(), "src", "app", "about", "page.tsx"), "utf8");
    expect(about).toMatch(/StatsBomb Open Data/);
  });

  it("no longer links to per-match replay pages or a 'classic replays' list", () => {
    const offenders = sourceFiles(join(process.cwd(), "src"))
      .filter((f) => /replay\/\$\{|classic replay/i.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});
