import { describe, expect, it } from "vitest";
import { buildBallGeometry, truncatedIcosahedronPolygons } from "./ballGeometry";

describe("truncated icosahedron", () => {
  const polys = truncatedIcosahedronPolygons();

  it("has 12 pentagons and 20 hexagons", () => {
    expect(polys.filter((p) => p.kind === "pentagon")).toHaveLength(12);
    expect(polys.filter((p) => p.kind === "hexagon")).toHaveLength(20);
    expect(polys.filter((p) => p.kind === "pentagon").every((p) => p.corners.length === 5)).toBe(true);
    expect(polys.filter((p) => p.kind === "hexagon").every((p) => p.corners.length === 6)).toBe(true);
  });

  it("has 60 distinct vertices and 90 edges of equal length", () => {
    const key = (v: { x: number; y: number; z: number }) => [v.x, v.y, v.z].map((n) => n.toFixed(5)).join(",");
    const verts = new Set(polys.flatMap((p) => p.corners.map(key)));
    expect(verts.size).toBe(60);
    const lengths = new Map<string, number>();
    for (const p of polys)
      p.corners.forEach((c, i) => {
        const n = p.corners[(i + 1) % p.corners.length];
        const edge = [key(c), key(n)].sort().join("|");
        lengths.set(edge, c.distanceTo(n));
      });
    expect(lengths.size).toBe(90);
    const all = [...lengths.values()];
    expect(Math.max(...all) - Math.min(...all)).toBeLessThan(1e-6);
  });

  it("builds a closed-looking, outward-facing mesh whose panels bulge above the seams", () => {
    const g = buildBallGeometry();
    const pos = g.getAttribute("position");
    const nrm = g.getAttribute("normal");
    let outward = 0;
    let rMin = Infinity;
    let rMax = 0;
    for (let i = 0; i < pos.count; i++) {
      const r = Math.hypot(pos.getX(i), pos.getY(i), pos.getZ(i));
      rMin = Math.min(rMin, r);
      rMax = Math.max(rMax, r);
      if (pos.getX(i) * nrm.getX(i) + pos.getY(i) * nrm.getY(i) + pos.getZ(i) * nrm.getZ(i) > 0) outward++;
    }
    expect(outward / pos.count).toBeGreaterThan(0.98);
    expect(rMax - rMin).toBeGreaterThan(0.03); // bulge + recessed seams are really there
    expect(rMax).toBeLessThan(1.05);
    expect(g.getAttribute("color")).toBeTruthy();
  });
});
