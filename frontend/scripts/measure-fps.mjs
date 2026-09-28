// Frames per second while scrolling the home page at 1440px (glass cards on), with the 3D
// ball vs. without it (reduced motion -> static image). Real GPU via ANGLE/Metal.
//   node scripts/measure-fps.mjs [baseUrl]
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:3000";
const ARGS = ["--use-angle=metal", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"];

async function run(label, ctxOptions, extra = async () => {}, args = ARGS) {
  const browser = await chromium.launch({ args });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ...ctxOptions });
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.waitForTimeout(3500);
  await extra(page);
  const hasCanvas = await page.evaluate(() => !!document.querySelector("canvas"));
  await page.evaluate(() => {
    window.__frames = [];
    let last = performance.now();
    const loop = (t) => { window.__frames.push(t - last); last = t; window.__raf = requestAnimationFrame(loop); };
    window.__raf = requestAnimationFrame(loop);
  });
  // ~6s of wheel scrolling: down then back up, ~60 wheel events/s
  const start = Date.now();
  for (let i = 0; i < 180; i++) { await page.mouse.wheel(0, i < 90 ? 45 : -45); await page.waitForTimeout(16); }
  const seconds = (Date.now() - start) / 1000;
  const frames = await page.evaluate(() => { cancelAnimationFrame(window.__raf); return window.__frames.slice(2); });
  const sorted = [...frames].sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)];
  const fps = frames.length / seconds;
  const gl = await page.evaluate(() => { const c = document.createElement("canvas"); const g = c.getContext("webgl"); const e = g && g.getExtension("WEBGL_debug_renderer_info"); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : "n/a"; });
  console.log(`${label.padEnd(34)} canvas=${String(hasCanvas).padEnd(5)} ${fps.toFixed(1)} fps  (p95 frame ${p95.toFixed(1)} ms, worst ${sorted[sorted.length - 1].toFixed(0)} ms, ${frames.length} frames / ${seconds.toFixed(1)}s)`);
  await browser.close();
  return { fps, gl };
}

const throttle = (rate) => async (page) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate });
};
const withBall = await run("3D ball ON, scrolling", {});
const noBall = await run("static ball (reduced motion), scrolling", { reducedMotion: "reduce" });
await run("3D ball ON, 4x CPU throttle", {}, throttle(4));
await run("static ball, 4x CPU throttle", { reducedMotion: "reduce" }, throttle(4));
await run("3D ball ON, software GL (no GPU)", {}, async () => {}, []);
await run("static ball, software GL (no GPU)", { reducedMotion: "reduce" }, async () => {}, []);
console.log(`GPU: ${withBall.gl}`);
console.log(`ball cost while scrolling: ${(noBall.fps - withBall.fps).toFixed(1)} fps`);
