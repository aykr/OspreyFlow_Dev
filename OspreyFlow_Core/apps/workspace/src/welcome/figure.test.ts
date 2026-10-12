// ADR-115 E2: the welcome page's product figure — a synthetic Operation Ledger network, drawn the way
// the canvas draws one (DESIGN.md §3.4 shapes and channels, §3.7 states, §3.8 provenance strokes).
// Seeded, so every visitor and every test sees the same picture.
import { describe, expect, it } from "vitest";

import { buildFigure, timelineBars } from "./figure";

describe("the welcome figure", () => {
  const figure = buildFigure();

  it("is the same picture every time, of the size the header counts", () => {
    expect(buildFigure()).toEqual(figure);
    expect([figure.nodes.length, figure.edges.length]).toEqual([56, 69]);
  });

  it("traces one path between groups in primary text, and selects one hub in brass", () => {
    const path = figure.edges.filter((e) => e.path);
    expect(path).toHaveLength(3);
    expect(figure.selected).toEqual({ x: 360, y: 92 });
  });

  it("draws provenance by stroke only: solid, 4 3 dashed, 1 3 dotted", () => {
    expect(new Set(figure.edges.map((e) => e.dash))).toEqual(new Set(["", "4 3", "1 3"]));
  });

  it("dims one group toward the panel, its label kept", () => {
    const dimmed = figure.nodes.filter((n) => n.dim);
    expect(dimmed.length).toBeGreaterThan(5);
    expect(dimmed.every((n) => n.fill.startsWith("color-mix(in oklab, var(--ch-"))).toBe(true);
    expect(figure.labels.find((l) => l.text === "Brightpath Consulting Ltd")?.dim).toBe(true);
  });

  it("names identifiers in mono and every other label in the interface face", () => {
    expect(figure.labels.filter((l) => l.mono).map((l) => l.text)).toEqual(["60-16-13 ••19"]);
  });

  it("has a 28-bar timeline whose window is drawn in the darker step", () => {
    const { bars, from, to } = timelineBars();
    expect(bars).toHaveLength(28);
    expect(bars.filter((b) => b.inWindow).length).toBe(to - from + 1);
    expect(bars.every((b) => b.height >= 3)).toBe(true);
  });
});
