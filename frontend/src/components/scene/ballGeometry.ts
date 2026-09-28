import { BufferGeometry, Float32BufferAttribute, Vector3 } from "three";
import { mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// A soccer-ball shape built from first principles: a truncated icosahedron (12 pentagons,
// 20 hexagons, 60 vertices, 90 edges) made by cutting every icosahedron corner off at 1/3 of
// each edge. Each polygon is tessellated as a fan of subdivided wedges, pushed out to a sphere
// and then displaced so the panels bulge (inflated leather) and drop into thin recessed seams.
// No logos, text or brand patterns - just panels.

export type Polygon = { kind: "pentagon" | "hexagon"; corners: Vector3[] };

const PHI = (1 + Math.sqrt(5)) / 2;

export function truncatedIcosahedronPolygons(): Polygon[] {
  // Icosahedron: cyclic permutations of (0, +-1, +-phi). Edge length is 2.
  const base: [number, number, number][] = [];
  for (const a of [-1, 1]) for (const b of [-PHI, PHI]) base.push([0, a, b], [a, b, 0], [b, 0, a]);
  const v = base.map(([x, y, z]) => new Vector3(x, y, z));

  const near = (i: number, j: number) => Math.abs(v[i].distanceTo(v[j]) - 2) < 1e-6;
  const faces: [number, number, number][] = [];
  for (let i = 0; i < 12; i++)
    for (let j = i + 1; j < 12; j++)
      for (let k = j + 1; k < 12; k++) if (near(i, j) && near(j, k) && near(i, k)) faces.push([i, j, k]);

  const third = (i: number, j: number) => v[i].clone().lerp(v[j], 1 / 3); // point 1/3 of the way i -> j
  const polygons: Polygon[] = [];

  // 20 hexagons, one per icosahedron face: two cut points on each of its three edges.
  for (const [a, b, c] of faces) {
    polygons.push({
      kind: "hexagon",
      corners: [third(a, b), third(b, a), third(b, c), third(c, b), third(c, a), third(a, c)],
    });
  }

  // 12 pentagons, one per icosahedron vertex: the cut point toward each of its 5 neighbours,
  // ordered by angle around the vertex.
  for (let i = 0; i < 12; i++) {
    const axis = v[i].clone().normalize();
    const neighbours = v.map((_, j) => j).filter((j) => j !== i && near(i, j));
    const ref = new Vector3().subVectors(v[neighbours[0]], v[i]).normalize();
    const side = new Vector3().crossVectors(axis, ref).normalize();
    const angle = (j: number) => {
      const d = new Vector3().subVectors(v[j], v[i]).normalize();
      return Math.atan2(d.dot(side), d.dot(ref));
    };
    neighbours.sort((p, q) => angle(p) - angle(q));
    polygons.push({ kind: "pentagon", corners: neighbours.map((j) => third(i, j)) });
  }
  return polygons;
}

const smoothstep = (lo: number, hi: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

export type BallShape = {
  radius: number;
  bulge: number; // how far panel centres rise above the seam line (fraction of radius)
  seamDepth: number; // how far the seam drops below the panel edge (fraction of radius)
  emboss: number; // extra raise of the pentagon panels (fraction of radius)
  subdivisions: number;
};

export const DEFAULT_SHAPE: BallShape = { radius: 1, bulge: 0.028, seamDepth: 0.016, emboss: 0.006, subdivisions: 7 };

const WHITE = [0.96, 0.975, 1.0];
const NAVY = [0.012, 0.028, 0.085];
const SEAM_WHITE = [0.5, 0.56, 0.68];
const SEAM_NAVY = [0.01, 0.02, 0.06];

export function buildBallGeometry(shape: BallShape = DEFAULT_SHAPE): BufferGeometry {
  const { radius, bulge, seamDepth, emboss, subdivisions: N } = shape;
  const positions: number[] = [];
  const colors: number[] = [];
  const uvs: number[] = [];
  const index: number[] = [];

  truncatedIcosahedronPolygons().forEach((poly, polyIndex) => {
    const centre = poly.corners.reduce((acc, p) => acc.add(p), new Vector3()).divideScalar(poly.corners.length);
    const normal = centre.clone().normalize();
    const e1 = new Vector3().subVectors(poly.corners[0], centre).normalize();
    const e2 = new Vector3().crossVectors(normal, e1);
    // Corner order differs per panel, so work out which way this one winds around its normal.
    const counterClockwise =
      new Vector3().crossVectors(new Vector3().subVectors(poly.corners[0], centre), new Vector3().subVectors(poly.corners[1], centre)).dot(normal) > 0;
    const isPentagon = poly.kind === "pentagon";
    const fill = isPentagon ? NAVY : WHITE;
    const seam = isPentagon ? SEAM_NAVY : SEAM_WHITE;
    const uvOffset = (polyIndex * 0.6180339) % 1; // decorrelates the grain between panels

    poly.corners.forEach((corner, k) => {
      const next = poly.corners[(k + 1) % poly.corners.length];
      const start = positions.length / 3;
      for (let i = 0; i <= N; i++) {
        const s = i / N; // 0 at the panel centre, 1 on its edge
        for (let j = 0; j <= N; j++) {
          const t = j / N;
          const flat = new Vector3()
            .subVectors(corner, centre)
            .addScaledVector(new Vector3().subVectors(next, corner), t)
            .multiplyScalar(s)
            .add(centre);
          const height =
            bulge * (1 - s * s) - seamDepth * smoothstep(0.82, 1, s) + (isPentagon ? emboss * (1 - smoothstep(0.55, 0.95, s)) : 0);
          const p = flat.normalize().multiplyScalar(radius * (1 + height));
          positions.push(p.x, p.y, p.z);
          const shade = smoothstep(0.9, 1, s);
          colors.push(
            fill[0] + (seam[0] - fill[0]) * shade,
            fill[1] + (seam[1] - fill[1]) * shade,
            fill[2] + (seam[2] - fill[2]) * shade
          );
          const local = new Vector3().subVectors(flat, centre);
          uvs.push(local.dot(e1) * 4 + uvOffset, local.dot(e2) * 4 + uvOffset);
        }
      }
      for (let i = 0; i < N; i++) {
        for (let j = 0; j < N; j++) {
          const a = start + i * (N + 1) + j;
          const b = a + 1;
          const c = a + (N + 1);
          const d = c + 1;
          // wound so the face normal points outward whichever way the panel's corners run
          if (counterClockwise) index.push(a, c, b, b, c, d);
          else index.push(a, b, c, b, d, c);
        }
      }
    });
  });

  let geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
  geometry.setIndex(index);
  // Weld wedge borders inside a panel (identical position/colour/uv) so shading is smooth
  // there; panels keep their own uv offsets, so seams between panels stay crisp.
  geometry = mergeVertices(geometry, 1e-5);
  geometry.computeVertexNormals();
  return geometry;
}
