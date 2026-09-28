"""One-off generator for frontend/public/scene/ball-lines.svg - a transparent line-art soccer ball.

Geometry: a truncated icosahedron. Its 60 vertices are all even (cyclic) permutations of
(0, +-1, +-3phi), (+-1, +-(2+phi), +-2phi), (+-phi, +-2, +-(2phi+1)); its 90 edges join the
vertex pairs at the minimum distance (2). The 12 pentagons sit around the icosahedron
directions (0, +-1, +-phi) and their cyclic permutations (each panel = the 5 nearest vertices);
the 20 hexagons sit around the dodecahedron directions (+-1, +-1, +-1) and (0, +-phi, +-1/phi)
cyclic (the 6 nearest vertices).

The vertices are normalised onto a sphere and every edge is drawn as a great-circle arc
(16 segments), so seams curve like a real ball. A pentagon is rotated slightly off-centre
(about 20 degrees), the sphere is projected orthographically, and arcs are split exactly at
the horizon (z = 0) into a front part and a faint back part - so the ball reads as see-through
and nothing bleeds past the outline circle.

NOTHING is filled: the ball, its panels and the circle are outlines only; the background shows
through everywhere. The glow is a blurred duplicate of the lines, not a filled shape. No logos,
no text.

Run: python scripts/make_ball_svg.py
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "scene" / "ball-lines.svg"

PHI = (1 + math.sqrt(5)) / 2
SIZE = 400  # viewBox is SIZE x SIZE; stroke widths below are in these units
CENTRE = SIZE / 2
RADIUS = 186  # leaves room for the glow inside the viewBox
ARC_SEGMENTS = 16
TILT_DEGREES = 20  # how far the nearest pentagon sits off the view axis
ROLL_DEGREES = -14
LINE_WIDTH = 1.5  # ~1.5px at 400px width
LINE_OPACITY = 0.55
BACK_FRACTION = 0.25  # back-facing seams are ~25% of the front line opacity
COLOR_FROM, COLOR_TO = "#7db2ff", "#3d7bff"


def even_permutations(base: tuple[float, float, float]) -> set[tuple[float, float, float]]:
    """All sign combinations of the cyclic (even) permutations of `base`."""
    out: set[tuple[float, float, float]] = set()
    x, y, z = base
    for a, b, c in ((x, y, z), (y, z, x), (z, x, y)):
        for sa, sb, sc in itertools.product((1, -1), repeat=3):
            out.add((round(sa * a, 9), round(sb * b, 9), round(sc * c, 9)))
    return out


def truncated_icosahedron() -> tuple[np.ndarray, list[tuple[int, int]], list[list[int]], list[list[int]]]:
    verts = (
        even_permutations((0, 1, 3 * PHI))
        | even_permutations((1, 2 + PHI, 2 * PHI))
        | even_permutations((PHI, 2, 2 * PHI + 1))
    )
    v = np.array(sorted(verts))
    assert len(v) == 60, f"expected 60 vertices, got {len(v)}"

    dist = np.linalg.norm(v[:, None, :] - v[None, :, :], axis=2)
    np.fill_diagonal(dist, np.inf)
    edge_len = dist.min()
    assert abs(edge_len - 2) < 1e-6, f"minimum distance should be 2, got {edge_len}"
    edges = [(i, j) for i in range(60) for j in range(i + 1, 60) if abs(dist[i, j] - edge_len) < 1e-6]
    assert len(edges) == 90, f"expected 90 edges, got {len(edges)}"

    def panel(axis: tuple[float, float, float], size: int) -> list[int]:
        d = np.array(axis) / np.linalg.norm(axis)
        dots = (v / np.linalg.norm(v, axis=1, keepdims=True)) @ d
        nearest = np.argsort(-dots)[:size]
        assert np.allclose(dots[nearest], dots[nearest[0]], atol=1e-9), "panel corners are not equidistant"
        return [int(i) for i in nearest]

    pent_dirs = even_permutations((0, 1, PHI))
    assert len(pent_dirs) == 12, len(pent_dirs)
    pentagons = [panel(d, 5) for d in sorted(pent_dirs)]

    hex_dirs = {(sx, sy, sz) for sx, sy, sz in itertools.product((1.0, -1.0), repeat=3)} | even_permutations(
        (0, PHI, 1 / PHI)
    )
    assert len(hex_dirs) == 20, len(hex_dirs)
    hexagons = [panel(d, 6) for d in sorted(hex_dirs)]
    assert len(pentagons) == 12 and len(hexagons) == 20
    return v, edges, pentagons, hexagons


def rotation_matrix(v: np.ndarray, pentagon: list[int]) -> np.ndarray:
    """Turn the sphere so a pentagon sits TILT_DEGREES off the view axis (+z, toward the viewer)."""
    axis = v[pentagon].mean(axis=0)
    axis /= np.linalg.norm(axis)
    z = np.array([0.0, 0.0, 1.0])
    k = np.cross(axis, z)
    s, c = np.linalg.norm(k), float(axis @ z)
    if s < 1e-12:
        align = np.eye(3)
    else:
        k /= s
        kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        align = np.eye(3) + s * kx + (1 - c) * (kx @ kx)  # Rodrigues: axis -> +z

    def rot(a: float, about: str) -> np.ndarray:
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        if about == "x":
            return np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
        return np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])

    return rot(ROLL_DEGREES, "z") @ rot(TILT_DEGREES, "x") @ align


def great_circle(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """n+1 points along the great-circle arc between unit vectors a and b."""
    omega = math.acos(max(-1.0, min(1.0, float(a @ b))))
    t = np.linspace(0, 1, n + 1)[:, None]
    return (np.sin((1 - t) * omega) * a + np.sin(t * omega) * b) / math.sin(omega)


def split_at_horizon(points: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Split a polyline of unit-sphere points into front (z >= 0) and back (z < 0) runs,
    inserting the exact horizon crossing so the two runs meet on the outline circle."""
    front: list[np.ndarray] = []
    back: list[np.ndarray] = []
    run = [points[0]]
    is_front = points[0][2] >= 0
    for p, q in itertools.pairwise(points):
        if (p[2] >= 0) == (q[2] >= 0):
            run.append(q)
            continue
        t = p[2] / (p[2] - q[2])
        cross = p + t * (q - p)
        cross = cross / np.linalg.norm(cross)
        cross[2] = 0.0
        cross = cross / np.linalg.norm(cross)
        run.append(cross)
        (front if is_front else back).append(np.array(run))
        run = [cross, q]
        is_front = not is_front
    (front if is_front else back).append(np.array(run))
    return front, back


def to_path(runs: list[np.ndarray]) -> str:
    parts = []
    for run in runs:
        pts = [(CENTRE + RADIUS * p[0], CENTRE - RADIUS * p[1]) for p in run]
        parts.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts))
    return " ".join(parts)


def build_svg() -> str:
    v, edges, pentagons, _hexagons = truncated_icosahedron()
    unit = v / np.linalg.norm(v, axis=1, keepdims=True)
    unit = unit @ rotation_matrix(v, pentagons[0]).T

    front_runs: list[np.ndarray] = []
    back_runs: list[np.ndarray] = []
    for i, j in edges:
        f, b = split_at_horizon(great_circle(unit[i], unit[j], ARC_SEGMENTS))
        front_runs += f
        back_runs += b

    front_d, back_d = to_path(front_runs), to_path(back_runs)
    back_opacity = LINE_OPACITY * BACK_FRACTION
    stroke = f'fill="none" stroke-width="{LINE_WIDTH}" stroke-linecap="round" stroke-linejoin="round"'
    lines = (
        f'<circle cx="{CENTRE}" cy="{CENTRE}" r="{RADIUS}" {stroke} stroke="url(#g)" stroke-opacity="{LINE_OPACITY}"/>\n'
        f'    <path d="{front_d}" {stroke} stroke="url(#g)" stroke-opacity="{LINE_OPACITY}"/>\n'
        f'    <path d="{back_d}" {stroke} stroke="url(#g)" stroke-opacity="{back_opacity:.4f}"/>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}" fill="none" aria-hidden="true">
  <defs>
    <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="20" y1="20" x2="{SIZE - 20}" y2="{SIZE - 20}">
      <stop offset="0" stop-color="{COLOR_FROM}"/>
      <stop offset="1" stop-color="{COLOR_TO}"/>
    </linearGradient>
    <filter id="glow" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="5"/>
    </filter>
    <g id="lines" fill="none">
    {lines}
    </g>
  </defs>
  <!-- soft glow: a blurred duplicate of the same lines (no filled shapes anywhere) -->
  <use href="#lines" xlink:href="#lines" filter="url(#glow)" opacity="0.9"/>
  <use href="#lines" xlink:href="#lines"/>
</svg>
"""


if __name__ == "__main__":
    svg = build_svg()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg)
    print(f"wrote {OUT} ({len(svg) / 1024:.1f} KB): 60 vertices, 90 edges, 12 pentagons, 20 hexagons")
