// Bilinear georeferencing across a 4-control-point quadrilateral — a
// direct TypeScript port of `packages/geo/bilinear.py`, kept deliberately
// identical in shape and naming. This is not shared code with the server
// (there is no cross-language import boundary in this repo to exploit),
// so the two exist independently by necessity: this one drives the
// wizard's live grid preview client-side, before the analyst confirms;
// `packages/geo/bilinear.py`'s is what the Conduit runs authoritatively
// once they do. Both are tested against the same known-answer fixture
// (an axis-aligned square control-point set must produce an evenly spaced
// grid) so the two cannot silently drift apart — see `bilinear.test.ts`
// and `tests/geo/test_bilinear.py`.
//
// Deliberately bilinear, not a general homography/projective transform —
// the same simple mapping MapLibre's own native `image` source uses to
// place a 4-corner raster, so the rendered image and the computed grid
// line up under the same maths. Control points are assumed to be given in
// a fixed winding order — top-left, top-right, bottom-right,
// bottom-left — a data-contract this module relies on but cannot itself
// verify from pixel content.

export interface ControlPoint {
  px: number;
  py: number;
  lon: number;
  lat: number;
}

export interface WorldPoint {
  lon: number;
  lat: number;
}

/** TL, TR, BR, BL, in that order. */
export type ControlQuad = readonly [
  ControlPoint,
  ControlPoint,
  ControlPoint,
  ControlPoint,
];

function bilinear(
  controlPoints: ControlQuad,
  u: number,
  v: number,
): WorldPoint {
  const [tl, tr, br, bl] = controlPoints;
  const topLon = tl.lon + (tr.lon - tl.lon) * u;
  const topLat = tl.lat + (tr.lat - tl.lat) * u;
  const bottomLon = bl.lon + (br.lon - bl.lon) * u;
  const bottomLat = bl.lat + (br.lat - bl.lat) * u;
  return {
    lon: topLon + (bottomLon - topLon) * v,
    lat: topLat + (bottomLat - topLat) * v,
  };
}

/** The signed area of the triangle `origin`->`a`->`b` (twice the area,
 * sign only meaningful relative to other calls with a consistent winding) —
 * the 2D cross product `(a - origin) x (b - origin)`. */
function crossProductZ(origin: WorldPoint, a: WorldPoint, b: WorldPoint): number {
  return (a.lon - origin.lon) * (b.lat - origin.lat) - (a.lat - origin.lat) * (b.lon - origin.lon);
}

// Below this, two points are treated as coincident/collinear rather than
// forming a genuine turn — not a georeferencing precision floor (this
// checkpoint's grids span real-world distances many orders of magnitude
// above it), just small enough that no legitimate click pair could land
// inside it by accident.
const _DEGENERATE_TURN_EPSILON = 1e-12;

/** True iff the four points, taken in the given TL/TR/BR/BL order, form a
 * simple (non-self-intersecting), consistently-wound quadrilateral — the
 * turn at every one of the four vertices has the same sign. Rejects the
 * "silent corruption" case a scrambled click order produces: swapping,
 * say, the BR and BL clicks crosses the quad into a bowtie, which
 * `computeGridCells`'s bilinear interpolation would still happily compute
 * a badly warped grid over without complaint — `SiteCalibrationWizard.tsx`
 * calls this right after the fourth map click, before persisting anything,
 * so a scrambled order is caught with a re-click prompt instead of
 * silently producing a corrupt grid. */
export function formsASimpleQuadrilateral(points: readonly WorldPoint[]): boolean {
  if (points.length !== 4) return false;
  const turns = points.map((_, i) => {
    const prev = points[(i - 1 + 4) % 4]!;
    const curr = points[i]!;
    const next = points[(i + 1) % 4]!;
    return crossProductZ(prev, curr, next);
  });
  if (turns.some((t) => Math.abs(t) < _DEGENERATE_TURN_EPSILON)) return false;
  return turns.every((t) => t > 0) || turns.every((t) => t < 0);
}

export interface GridCell {
  row: number;
  col: number;
  /** TL, TR, BR, BL — the same winding order as `controlPoints`. */
  corners: readonly [WorldPoint, WorldPoint, WorldPoint, WorldPoint];
  centroid: WorldPoint;
}

/** One `GridCell` per `(row, col)`, row-major, both zero-based counting
 * from the TL/TR edge — mirrors `packages/geo/bilinear.py`'s
 * `compute_grid_cells` exactly, including its row/col numbering. */
export function computeGridCells(
  controlPoints: ControlQuad,
  rows: number,
  cols: number,
): GridCell[] {
  if (rows < 1 || cols < 1) {
    throw new Error(
      `rows/cols must both be >= 1, got rows=${rows} cols=${cols}`,
    );
  }
  const cells: GridCell[] = [];
  for (let row = 0; row < rows; row++) {
    const v0 = row / rows;
    const v1 = (row + 1) / rows;
    const vMid = (row + 0.5) / rows;
    for (let col = 0; col < cols; col++) {
      const u0 = col / cols;
      const u1 = (col + 1) / cols;
      const uMid = (col + 0.5) / cols;
      cells.push({
        row,
        col,
        corners: [
          bilinear(controlPoints, u0, v0),
          bilinear(controlPoints, u1, v0),
          bilinear(controlPoints, u1, v1),
          bilinear(controlPoints, u0, v1),
        ],
        centroid: bilinear(controlPoints, uMid, vMid),
      });
    }
  }
  return cells;
}
