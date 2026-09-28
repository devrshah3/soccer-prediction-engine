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
const names = ["home (blue)", "draw (amber)", "away (rose)"];
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
