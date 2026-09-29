import { describe, expect, it } from "vitest";

import { embedPngTextChunks, readPngTextChunks } from "./pngMark";

// A real, valid 1x1 transparent PNG (68 bytes) — not a fabricated byte sequence. Verified
// independently before this test was written: signature bytes match the PNG spec, and the first
// chunk after the signature is a real 13-byte IHDR.
const MINIMAL_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function minimalPngBytes(): Uint8Array {
  const binary = atob(MINIMAL_PNG_BASE64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

describe("pngMark", () => {
  it("embeds a tEXt chunk that reads back with the exact value written", () => {
    const marked = embedPngTextChunks(minimalPngBytes(), { osprey_mark: "OspreyFlow" });
    const fields = readPngTextChunks(marked);
    expect(fields.osprey_mark).toBe("OspreyFlow");
  });

  it("embeds every field, not only the first", () => {
    const marked = embedPngTextChunks(minimalPngBytes(), {
      osprey_mark: "OspreyFlow",
      investigation_id: "inv-1",
      handling_level: "SECRET",
      exported_at: "2026-09-22T00:00:00Z",
      resolution_threshold: "0.95",
    });
    const fields = readPngTextChunks(marked);
    expect(fields).toEqual({
      osprey_mark: "OspreyFlow",
      investigation_id: "inv-1",
      handling_level: "SECRET",
      exported_at: "2026-09-22T00:00:00Z",
      resolution_threshold: "0.95",
    });
  });

  it("produces a byte sequence that is still a well-formed PNG after marking", () => {
    const marked = embedPngTextChunks(minimalPngBytes(), { osprey_mark: "OspreyFlow" });
    // The PNG signature survives unchanged, and the file still ends in a real IEND chunk —
    // "well-formed", not merely "longer".
    expect(Array.from(marked.slice(0, 8))).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const tail = marked.slice(marked.length - 8, marked.length - 4);
    expect(new TextDecoder().decode(tail)).toBe("IEND");
  });

  it("rejects a byte sequence with no real PNG signature rather than silently marking garbage", () => {
    const notAPng = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(() => embedPngTextChunks(notAPng, { osprey_mark: "OspreyFlow" })).toThrow();
    expect(() => readPngTextChunks(notAPng)).toThrow();
  });

  it("an unmarked PNG carries no mark fields at all — the negative control for the marking test", () => {
    const fields = readPngTextChunks(minimalPngBytes());
    expect(fields.osprey_mark).toBeUndefined();
  });
});
