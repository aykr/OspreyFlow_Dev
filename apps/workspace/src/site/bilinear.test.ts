import { describe, expect, it } from "vitest";

import { type ControlQuad, computeGridCells, formsASimpleQuadrilateral } from "./bilinear";

// Same fixtures as `tests/geo/test_bilinear.py`, deliberately — the two
// implementations must agree, and testing them against the same inputs is
// how a drift between them would actually get caught.
const SQUARE: ControlQuad = [
  { px: 0, py: 0, lon: -1.0, lat: 1.0 },
  { px: 100, py: 0, lon: 1.0, lat: 1.0 },
  { px: 100, py: 100, lon: 1.0, lat: -1.0 },
  { px: 0, py: 100, lon: -1.0, lat: -1.0 },
];

const SKEWED: ControlQuad = [
  { px: 0, py: 0, lon: 0.0, lat: 2.0 },
  { px: 100, py: 10, lon: 3.0, lat: 2.5 },
  { px: 90, py: 100, lon: 2.5, lat: -1.0 },
  { px: -10, py: 90, lon: -0.5, lat: -0.5 },
];

function byRowCol(cells: ReturnType<typeof computeGridCells>) {
  const map = new Map<string, (typeof cells)[number]>();
  for (const cell of cells) map.set(`${cell.row},${cell.col}`, cell);
  return map;
}

describe("computeGridCells", () => {
  it("produces an evenly spaced grid over a square control quad", () => {
    const cells = computeGridCells(SQUARE, 10, 10);
    expect(cells).toHaveLength(100);

    const byRc = byRowCol(cells);
    const first = byRc.get("0,0")!;
    const last = byRc.get("9,9")!;

    expect(first.centroid.lon).toBeCloseTo(-1.0 + 0.1);
    expect(first.centroid.lat).toBeCloseTo(1.0 - 0.1);
    expect(last.centroid.lon).toBeCloseTo(1.0 - 0.1);
    expect(last.centroid.lat).toBeCloseTo(-1.0 + 0.1);
  });

  it("matches the control points exactly at the grid's outer corners", () => {
    for (const controlPoints of [SQUARE, SKEWED]) {
      const cells = computeGridCells(controlPoints, 10, 10);
      const byRc = byRowCol(cells);
      const [tl, tr, br, bl] = controlPoints;

      expect(byRc.get("0,0")!.corners[0].lon).toBeCloseTo(tl.lon);
      expect(byRc.get("0,0")!.corners[0].lat).toBeCloseTo(tl.lat);
      expect(byRc.get("0,9")!.corners[1].lon).toBeCloseTo(tr.lon);
      expect(byRc.get("0,9")!.corners[1].lat).toBeCloseTo(tr.lat);
      expect(byRc.get("9,9")!.corners[2].lon).toBeCloseTo(br.lon);
      expect(byRc.get("9,9")!.corners[2].lat).toBeCloseTo(br.lat);
      expect(byRc.get("9,0")!.corners[3].lon).toBeCloseTo(bl.lon);
      expect(byRc.get("9,0")!.corners[3].lat).toBeCloseTo(bl.lat);
    }
  });

  it("shares corners exactly between adjacent cells, with no gap or overlap", () => {
    const cells = computeGridCells(SKEWED, 5, 5);
    const byRc = byRowCol(cells);

    const left = byRc.get("2,2")!;
    const right = byRc.get("2,3")!;
    expect(left.corners[1]).toEqual(right.corners[0]);
    expect(left.corners[2]).toEqual(right.corners[3]);

    const top = byRc.get("2,2")!;
    const bottom = byRc.get("3,2")!;
    expect(top.corners[3]).toEqual(bottom.corners[0]);
    expect(top.corners[2]).toEqual(bottom.corners[1]);
  });

  it("spans the whole quad for a single-cell grid", () => {
    const cells = computeGridCells(SKEWED, 1, 1);
    expect(cells).toHaveLength(1);
    const cell = cells[0]!;
    const [tl, tr, br, bl] = SKEWED;
    expect(cell.corners[0].lon).toBeCloseTo(tl.lon);
    expect(cell.corners[1].lon).toBeCloseTo(tr.lon);
    expect(cell.corners[2].lon).toBeCloseTo(br.lon);
    expect(cell.corners[3].lon).toBeCloseTo(bl.lon);
  });

  it("rejects a non-positive row or column count", () => {
    expect(() => computeGridCells(SQUARE, 0, 10)).toThrow(/rows\/cols/);
    expect(() => computeGridCells(SQUARE, 10, 0)).toThrow(/rows\/cols/);
    expect(() => computeGridCells(SQUARE, -1, 5)).toThrow(/rows\/cols/);
  });
});

describe("formsASimpleQuadrilateral", () => {
  it("accepts a properly wound square", () => {
    expect(formsASimpleQuadrilateral(SQUARE)).toBe(true);
  });

  it("accepts a properly wound, non-rectangular quad", () => {
    expect(formsASimpleQuadrilateral(SKEWED)).toBe(true);
  });

  it("rejects a bowtie produced by swapping the BR and BL clicks", () => {
    // The exact "scrambled click order" corruption case this check exists
    // for: TL, TR, BL, BR (third and fourth points swapped) crosses the
    // quad's two "bottom" edges over each other.
    const bowtie = [SQUARE[0], SQUARE[1], SQUARE[3], SQUARE[2]];
    expect(formsASimpleQuadrilateral(bowtie)).toBe(false);
  });

  it("rejects a bowtie produced by swapping the TL and TR clicks", () => {
    const bowtie = [SQUARE[1], SQUARE[0], SQUARE[2], SQUARE[3]];
    expect(formsASimpleQuadrilateral(bowtie)).toBe(false);
  });

  it("rejects three collinear points", () => {
    const degenerate = [
      { lon: -1, lat: 1 },
      { lon: 0, lat: 1 },
      { lon: 1, lat: 1 },
      { lon: 0, lat: -1 },
    ];
    expect(formsASimpleQuadrilateral(degenerate)).toBe(false);
  });

  it("rejects anything other than exactly four points", () => {
    expect(formsASimpleQuadrilateral(SQUARE.slice(0, 3))).toBe(false);
  });
});
