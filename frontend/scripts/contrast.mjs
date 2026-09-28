// Measures WCAG contrast of the three prediction-bar outcome colours against the glass card
// behind them, sampled from a real screenshot of the running app (so it includes whatever
// scene - e.g. the 3D ball - is currently painted behind the glass).
//   node scripts/contrast.mjs [baseUrl] [path]
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:3000";
const PATH = process.argv[3] ?? "/";
const lum = ([r, g, b]) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto(BASE + PATH, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
const boxes = await page.evaluate(() =>
  [...document.querySelectorAll('[role="img"][aria-label]')].slice(0, 12).map((bar) => {
    const r = bar.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height, segs: [...bar.children].map((c) => { const q = c.getBoundingClientRect(); return { cx: q.x + q.width / 2, cy: q.y + q.height / 2, w: q.width, op: getComputedStyle(c).opacity }; }) };
  }).filter((b) => b.y > 0 && b.y < 880)
);
const png = await page.screenshot({ type: "png" });
const px = await page.evaluate(async ({ b64, boxes }) => {
  const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
  const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
  const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
  const at = (x, y) => Array.from(ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data.slice(0, 3));
  return boxes.map((b) => ({ bg: at(b.x + 4, b.y - 6), segs: b.segs.map((s) => (s.w > 6 ? at(s.cx, s.cy) : null)) }));
}, { b64: png.toString("base64"), boxes });
const names = ["home (blue)", "draw (amber)", "away (teal)"];
const worst = [[], [], []];
const leaderVsDim = { leader: [], dim: [] };
px.forEach((p, i) => p.segs.forEach((c, k) => {
  if (!c) return;
  const r = ratio(c, p.bg);
  worst[k].push(r);
  (boxes[i].segs[k].op === "1" ? leaderVsDim.leader : leaderVsDim.dim).push(r);
}));
console.log(`${boxes.length} bars sampled on ${PATH} (1440px)`);
names.forEach((n, k) => worst[k].length && console.log(`${n.padEnd(13)} min ${Math.min(...worst[k]).toFixed(2)}:1  median ${worst[k].sort((a, b) => a - b)[Math.floor(worst[k].length / 2)].toFixed(2)}:1  (n=${worst[k].length})`));
const mm = (a) => (a.length ? `${Math.min(...a).toFixed(2)}:1` : "n/a");
console.log(`leader segments min ${mm(leaderVsDim.leader)} | dimmed segments min ${mm(leaderVsDim.dim)}  (WCAG non-text UI target: 3:1)`);
await browser.close();

// ---- Text contrast over the scene (incl. the ball): hide all text, screenshot the real
// backdrop, sample the pixels behind every text run, compare with the text's own colour.
{
  const b2 = await chromium.launch({ args: ["--use-angle=metal", "--ignore-gpu-blocklist"] });
  const p2 = await b2.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await p2.goto(BASE + PATH, { waitUntil: "networkidle" });
  await p2.waitForTimeout(2500);
  const runs = await p2.evaluate(() => {
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim() || !n.parentElement || n.parentElement.closest("nextjs-portal, script, style")) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > 890) continue;
      const cs = getComputedStyle(n.parentElement);
      const m = cs.color.match(/[\d.]+/g).map(Number);
      const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
      out.push({ text: n.textContent.trim().slice(0, 28), x: r.x, y: r.y, w: r.width, h: r.height, color: m.slice(0, 3), alpha: m[3] ?? 1, large: size >= 24 || (size >= 18.66 && bold) });
    }
    return out;
  });
  await p2.addStyleTag({ content: "* { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; } nextjs-portal { display: none !important; }" });
  await p2.waitForTimeout(300);
  const shot = await p2.screenshot({ type: "png" });
  const samples = await p2.evaluate(async ({ b64, runs }) => {
    const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
    const at = (x, y) => Array.from(ctx.getImageData(Math.max(0, Math.min(img.width - 1, Math.round(x))), Math.max(0, Math.min(img.height - 1, Math.round(y))), 1, 1).data.slice(0, 3));
    return runs.map((r) => [[.1, .5], [.5, .5], [.9, .5], [.5, .15], [.5, .85]].map(([fx, fy]) => at(r.x + r.w * fx, r.y + r.h * fy)));
  }, { b64: shot.toString("base64"), runs });
  const results = runs.map((r, i) => {
    let worst = Infinity;
    for (const bg of samples[i]) {
      const fg = r.color.map((c, k) => c * r.alpha + bg[k] * (1 - r.alpha)); // composite text alpha over its backdrop
      worst = Math.min(worst, ratio(fg, bg));
    }
    return { ...r, worst };
  });
  const over = results.filter((r) => r.x + r.w > 850 && r.y < 800); // the region the ball can sit behind
  const need = (r) => (r.large ? 3 : 4.5);
  const report = (label, arr) => {
    const bad = arr.filter((r) => r.worst < need(r));
    const min = arr.reduce((a, r) => (r.worst < a.worst ? r : a), arr[0]);
    console.log(`${label}: ${arr.length} text runs, min ${min.worst.toFixed(2)}:1 ("${min.text}"), ${bad.length} below WCAG AA (4.5:1 normal / 3:1 large)`);
    bad.slice(0, 40).forEach((r) => console.log(`   ${r.worst.toFixed(2)}:1  "${r.text}" at (${Math.round(r.x)},${Math.round(r.y)}) rgb(${r.color.join(",")})`));
  };
  report("all visible text     ", results);
  report("text over ball region", over);
  await b2.close();
}
