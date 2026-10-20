import { describe, expect, it } from "vitest";

import { readPngTextChunks } from "./pngMark";
import { chartMarkFields, embedChartMark } from "./chartExport";
import type { ExportMark } from "./api";

// The same real, valid 1x1 PNG fixture `pngMark.test.ts` already uses — stands in for whatever
// bytes `stageImage` (untestable in this environment, see `chartExport.ts`'s own module
// docstring) would have produced from a live canvas.
const MINIMAL_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function minimalPngBytes(): Uint8Array {
  const binary = atob(MINIMAL_PNG_BASE64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

const MARK: ExportMark = {
  osprey_mark: "OspreyFlow",
  investigation_id: "inv-1",
  exported_at: "2026-09-23T00:00:00Z",
  resolution_threshold: 0.95,
  handling_level: "SECRET",
};

describe("chart export — test_chart_export_produces_a_real_png_carrying_the_mark", () => {
  it("produces a well-formed PNG (real signature, real IEND) carrying every mark field", () => {
    const marked = embedChartMark(minimalPngBytes(), MARK);

    // Well-formed in its own format — the same structural check `pngMark.test.ts` already
    // establishes, not merely "some bytes came back".
    expect(Array.from(marked.slice(0, 8))).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const tail = marked.slice(marked.length - 8, marked.length - 4);
    expect(new TextDecoder().decode(tail)).toBe("IEND");

    // Carries the mark — every field, read back through the real chunk reader, not asserted
    // against the input object directly.
    const fields = readPngTextChunks(marked);
    expect(fields).toEqual({
      osprey_mark: "OspreyFlow",
      investigation_id: "inv-1",
      exported_at: "2026-09-23T00:00:00Z",
      resolution_threshold: "0.95",
      handling_level: "SECRET",
    });
  });

  it("stringifies resolution_threshold, since a PNG tEXt chunk only ever carries text", () => {
    const fields = chartMarkFields({ ...MARK, resolution_threshold: 0.8 });
    expect(fields.resolution_threshold).toBe("0.8");
    expect(typeof fields.resolution_threshold).toBe("string");
  });

  it("an artefact that skipped marking is distinguishable from one that carries it — the negative control", () => {
    const fields = readPngTextChunks(minimalPngBytes());
    expect(fields.osprey_mark).toBeUndefined();
  });
});
