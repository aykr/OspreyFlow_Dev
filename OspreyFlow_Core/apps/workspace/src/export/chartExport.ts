// Chart export — Phase 8 Stage 4h, `02_GLASS_FRONTEND.md` §10.1 ("Chart — PNG,
// `@sigma/export-image`'s own native output for the canvas case") and §10.3 ("a chart gets a
// visible footer/watermark plus embedded machine-readable image metadata carrying the same
// fields").
//
// **Split into two functions on purpose, not merged into one.** `embedChartMark` is pure —
// PNG bytes in, marked PNG bytes out — and is what `chartExport.test.ts` proves against a real,
// fixed PNG fixture (the same one `pngMark.test.ts` already uses). `captureChartImage` is the real
// browser integration: a live `Sigma` instance, `@sigma/export-image`'s own `toBlob`, and
// `OffscreenCanvas`/`createImageBitmap` to composite the visible watermark onto the captured
// pixels before the machine-readable mark is embedded. **`captureChartImage` cannot be exercised
// in this project's own vitest environment** — `vitest.config.ts`'s own default `node` environment
// has no WebGL context for Sigma to render into, and no existing test in this codebase mounts a
// real `GlassCanvas`/`Sigma` instance at all (checked directly: `src/canvas/*.test.ts` are pure
// data-transform tests, never a render); `OffscreenCanvas`/`createImageBitmap` are real browser
// APIs `jsdom` does not implement either. This is the same class of disclosed gap `GlassCanvas.tsx`
// already carries for `highlightNodes` (real-renderer-dependent, proven by contract not by a
// vitest render) — trusted to the real, already-tested `@sigma/export-image` library and to a
// human/Playwright check against the real app, not asserted here as if it were unit-tested.
// `@sigma/export-image`/`sigma` are imported dynamically inside `captureChartImage`, not at
// module top level — `sigma`'s own module body references `WebGL2RenderingContext` at import
// time (confirmed directly: a static import here throws `ReferenceError:
// WebGL2RenderingContext is not defined` in vitest's `node` environment, before any test in
// this file runs), which would make `embedChartMark`/`chartMarkFields` — the pure, tested half
// of this module — untestable too. A dynamic import confines that requirement to the one
// function that is genuinely real-browser-only.
import type { Attributes } from "graphology-types";
import type Sigma from "sigma";

import { embedPngTextChunks } from "./pngMark";
import type { ExportMark } from "./api";

/** The mark's own fields, flattened to the string keyword/text pairs a PNG `tEXt` chunk can carry
 * — every `ExportMark` field, `resolution_threshold` stringified since PNG text chunks are text
 * only. */
export function chartMarkFields(mark: ExportMark): Record<string, string> {
  return {
    osprey_mark: mark.osprey_mark,
    investigation_id: mark.investigation_id,
    exported_at: mark.exported_at,
    resolution_threshold: String(mark.resolution_threshold),
    handling_level: mark.handling_level,
  };
}

/** Pure: embeds the mark's own fields into `pngBytes` as `tEXt` chunks
 * (`02_GLASS_FRONTEND.md` §10.3's "embedded machine-readable image metadata"). Throws if
 * `pngBytes` is not a real PNG — `embedPngTextChunks`'s own "fail loudly, never dropped silently"
 * posture, unchanged here. */
export function embedChartMark(pngBytes: Uint8Array, mark: ExportMark): Uint8Array {
  return embedPngTextChunks(pngBytes, chartMarkFields(mark));
}

/** The visible watermark text — one line, bottom-right, the same fields the embedded metadata
 * carries so a human reading the image and a system reading its metadata agree on what the mark
 * says (`02_GLASS_FRONTEND.md` §10.3's own "carrying the same fields"). */
export function chartWatermarkText(mark: ExportMark): string {
  return `${mark.osprey_mark} · ${mark.investigation_id} · ${mark.handling_level} · ${mark.exported_at}`;
}

/** The real capture path: `toBlob` (a live `Sigma` renderer → PNG bytes, `@sigma/export-image`'s
 * own job, not reimplemented here) → a visible watermark composited via `OffscreenCanvas` →
 * `embedChartMark`'s own machine-readable metadata. Returns a `Blob` ready to download. */
export async function captureChartImage<
  N extends Attributes = Attributes,
  E extends Attributes = Attributes,
  G extends Attributes = Attributes,
>(sigma: Sigma<N, E, G>, mark: ExportMark): Promise<Blob> {
  const { toBlob } = await import("@sigma/export-image");
  // `toBlob`'s own signature only cares about the generic `Sigma` (default `Attributes` type
  // params) — it never reads a caller's own node/edge attribute shape, so this cast is safe: it
  // widens, it does not lie about what the renderer actually holds.
  const rawBlob = await toBlob(sigma as unknown as Sigma, { format: "png" });
  const bitmap = await createImageBitmap(rawBlob);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("captureChartImage: 2D canvas context unavailable");
  }
  ctx.drawImage(bitmap, 0, 0);
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "rgba(0, 0, 0, 0.75)";
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText(chartWatermarkText(mark), bitmap.width - 8, bitmap.height - 8);
  const watermarked = await canvas.convertToBlob({ type: "image/png" });
  const bytes = new Uint8Array(await watermarked.arrayBuffer());
  const marked = embedChartMark(bytes, mark);
  return new Blob([marked.slice().buffer], { type: "image/png" });
}
