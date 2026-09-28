// Renders the SAME 3D ball the site uses to a transparent WebP (public/scene/ball.webp) - the
// static fallback for mobile, reduced motion, Save-Data and no-WebGL. Needs the dev server.
//   node scripts/render-ball-fallback.mjs [baseUrl]
import { writeFileSync, mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:3000";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "scene", "ball.webp");
const LIMIT = 150 * 1024;
mkdirSync(dirname(OUT), { recursive: true });

const browser = await chromium.launch({ args: ["--use-angle=metal", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1100, height: 1100 }, deviceScaleFactor: 1 });
await page.goto(`${BASE}/dev/ball`, { waitUntil: "networkidle" });
await page.waitForFunction(() => typeof window.__ballCapture === "function");
let quality = 0.9;
let bytes;
for (; quality >= 0.4; quality -= 0.05) {
  const url = await page.evaluate(([q]) => window.__ballCapture(0.9, q), [quality]);
  bytes = Buffer.from(url.split(",")[1], "base64");
  if (bytes.length <= LIMIT) break;
}
writeFileSync(OUT, bytes);
console.log(`ball.webp ${(statSync(OUT).size / 1024).toFixed(1)} KB at quality ${quality.toFixed(2)} (limit 150 KB)`);
await browser.close();
if (statSync(OUT).size > LIMIT) process.exit(1);
