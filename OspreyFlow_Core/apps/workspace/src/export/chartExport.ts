// Chart export — Phase 8 Stage 4h, `02_GLASS_FRONTEND.md` §10.1 ("Chart — PNG", the canvas as
// drawn: `stageImage` below, ADR-118) and §10.3 ("a chart gets a
// visible footer/watermark plus embedded machine-readable image metadata carrying the same
// fields").
//
// **Split into two functions on purpose, not merged into one.** `embedChartMark` is pure —
// PNG bytes in, marked PNG bytes out — and is what `chartExport.test.ts` proves against a real,
// fixed PNG fixture (the same one `pngMark.test.ts` already uses). `captureChartImage` is the real
// browser integration: a live `Sigma` instance, its own stage canvas (`stageImage`), and
// `OffscreenCanvas`/`createImageBitmap` to composite the visible watermark onto the captured
// pixels before the machine-readable mark is embedded. **`captureChartImage` cannot be exercised
// in this project's own vitest environment** — `vitest.config.ts`'s own default `node` environment
// has no WebGL context for Sigma to render into, and no existing test in this codebase mounts a
// real `GlassCanvas`/`Sigma` instance at all (checked directly: `src/canvas/*.test.ts` are pure
// data-transform tests, never a render); `OffscreenCanvas`/`createImageBitmap` are real browser
// APIs `jsdom` does not implement either. This is the same class of disclosed gap `GlassCanvas.tsx`
// already carries for `highlightNodes` (real-renderer-dependent, proven by contract not by a
// vitest render) — proven instead by `export-capture/capture.spec.ts` against the real canvas in a
// browser, not asserted here as if it were unit-tested. Nothing from `sigma` is imported here but
// its type: `sigma`'s own module body references `WebGL2RenderingContext` at import time (a
// static import throws `ReferenceError: WebGL2RenderingContext is not defined` in vitest's `node`
// environment), which would make `embedChartMark`/`chartMarkFields` — the pure, tested half of this
// module — untestable too.
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

/** The canvas as it is drawn now, as PNG bytes: the renderer's own stage, read straight after it
 * draws (WebGL keeps its picture only until the frame is shown, and `toBlob` copies it at the
 * call). Sigma 4 draws nodes, links and labels on that one canvas. `@sigma/export-image` was not
 * used for this under Sigma 4: it draws a second renderer from the first's primitives, styles and
 * settings, without its reducers, and the Glass's whole look — pictures, rings, line patterns,
 * label colours — is the reducers' (`GlassCanvas.tsx`). */
export function stageImage(sigma: {
  getStageCanvas(): HTMLCanvasElement;
  on(event: "afterRender", listener: () => void): unknown;
  off(event: "afterRender", listener: () => void): unknown;
  scheduleRender(): unknown;
}): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const grab = () => {
      sigma.off("afterRender", grab);
      sigma
        .getStageCanvas()
        .toBlob((blob) => (blob ? resolve(blob) : reject(new Error("stageImage: the canvas gave no image"))), "image/png");
    };
    sigma.on("afterRender", grab);
    sigma.scheduleRender();
  });
}

/** The real capture path: the canvas as drawn (`stageImage`) → PNG bytes → a visible watermark
 * composited via `OffscreenCanvas` → `embedChartMark`'s own machine-readable metadata. Returns a
 * `Blob` ready to download. */
export async function captureChartImage<
  N extends Attributes = Attributes,
  E extends Attributes = Attributes,
  G extends Attributes = Attributes,
>(sigma: Sigma<N, E, G>, mark: ExportMark): Promise<Blob> {
  const rawBlob = await stageImage(sigma);
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
