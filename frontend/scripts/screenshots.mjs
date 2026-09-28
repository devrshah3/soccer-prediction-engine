// Visual QA (item 7): full-page screenshots of every main view at desktop (1440px) and
// phone (375px) widths against a running dev stack (frontend :3000, API :8000), saved as
// compressed JPEGs in ../reports/screenshots. Also fails if any page prints a raw league
// code or logs a console error - the same problems the unit tests guard, checked on the
// real rendered pages.
//
//   node scripts/screenshots.mjs [baseUrl]
import { mkdirSync, readdirSync, statSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:3000";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "reports", "screenshots");
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 375, height: 812 } };
const RAW_CODE = /\b(?:en|es|it|de|fr)\.1\b|\bCL\b/;

const PAGES = [
  { name: "home", path: "/" },
  { name: "leagues-hub", path: "/leagues" },
  { name: "league-premier-league-table-open", path: "/leagues/premier-league?view=table" },
  { name: "team-arsenal", path: "/teams/arsenal" },
  { name: "match-arsenal-leeds", path: "/matches/8097" },
  { name: "awards-current-season", path: "/awards" },
  { name: "awards-past-season-2024-25", path: "/awards?season=2024-25" },
  { name: "replay-yesterday", path: "/replay?tz=-240" },
];

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const problems = [];

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  const ctx = await browser.newContext({ viewport, timezoneId: "America/New_York", locale: "en-US" });
  const shoot = async (page, name, fullPage) => {
    await page.waitForTimeout(1200);
    await page.screenshot({ path: join(OUT, `${name}-${vpName}.jpg`), type: "jpeg", quality: 62, fullPage });
  };

  for (const { name, path } of PAGES) {
    const page = await ctx.newPage();
    const consoleErrors = [];
    page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text().slice(0, 200)));
    page.on("pageerror", (e) => consoleErrors.push(String(e).slice(0, 200)));
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    // The Sheet opens client-side from ?view=table; give hydration a moment.
    await shoot(page, name, true);
    const text = await page.evaluate(() => document.body.innerText);
    const leak = text.match(RAW_CODE);
    if (leak) problems.push(`${vpName} ${path}: raw league code "${leak[0]}" rendered`);
    if (consoleErrors.length) problems.push(`${vpName} ${path}: console errors: ${consoleErrors.join(" | ")}`);
    // overflow-x is hidden on html/body, so scrollWidth can't reveal clipped content - measure
    // the rightmost edge of any element in the page flow instead (fixed overlays and intentionally scrollable or truncated content excluded).
    const offenders = await page.evaluate((vw) => {
      return [...document.querySelectorAll("main *")]
        .filter((e) => getComputedStyle(e).position !== "fixed" && !e.closest(".overflow-x-auto, .truncate") && e.getBoundingClientRect().right > vw + 1)
        .slice(0, 3)
        .map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 50)} right=${Math.round(e.getBoundingClientRect().right)}`);
    }, viewport.width);
    if (offenders.length) problems.push(`${vpName} ${path}: content past the viewport edge: ${offenders.join(" ; ")}`);
    await page.close();
  }

  // The assistant: closed bubble over a page, then the docked popup, then maximized.
  const page = await ctx.newPage();
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.getByLabel("Open KickCast assistant").click();
  await shoot(page, "assistant-docked", false);
  await page.getByLabel("Expand to full screen").click();
  await shoot(page, "assistant-maximized", false);
  await page.close();
  await ctx.close();
}
await browser.close();

const files = readdirSync(OUT).map((f) => ({ f, kb: Math.round(statSync(join(OUT, f)).size / 1024) }));
const totalKb = files.reduce((n, x) => n + x.kb, 0);
console.log(files.map((x) => `${String(x.kb).padStart(5)} KB  ${x.f}`).join("\n"));
console.log(`total ${(totalKb / 1024).toFixed(2)} MB across ${files.length} screenshots`);
if (totalKb > 5 * 1024) problems.push(`screenshots total ${totalKb} KB, over the 5 MB budget`);
if (problems.length) {
  console.error("\nPROBLEMS:\n- " + problems.join("\n- "));
  process.exit(1);
}
console.log("no raw league codes, console errors or page-level horizontal overflow found");
