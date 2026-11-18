// GG6 (ADR-014 Amendment 2): the Map view draws tiles on `maplibre-gl` 6.x, in a real browser, offline.
//
// Nothing offline proved this before. `map-view-harness.tsx` gives MapLibre a raster provider whose
// tiles never arrive (it checks the camera, not the picture) and `live/basemap.spec.ts` needs a live
// stack. This spec drives the real `MapView` over a synthetic vector PMTiles archive
// (`mapTilesFixture.ts`) read through the real `pmtiles://` protocol path, and the same file runs twice:
// against the Vite dev server (`keyboard/playwright.config.ts`) and against a production bundle served
// by `vite preview` (`map-build/playwright.config.ts`). The production run is the one that can see the
// worker file: MapLibre 6 finds its worker beside the module that loads it, and a Vite production build
// does not emit one unless the Glass says where it is (`setWorkerUrl`).
//
// The archive is answered by this spec, as the Conduit's ranged `local-source` route answers a real one:
// 206 with `Content-Range` for a range, 416 for one past the end, and nothing for a path it does not hold.
// It models what the real route refuses as well as what it grants (CLAUDE.md rule 15).
import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { FIXTURE_FILE, SAMPLES, buildMapTilesFixture } from "./mapTilesFixture";

test.use({ viewport: { width: 1100, height: 800 } });

const FIXTURE = new Uint8Array(readFileSync(FIXTURE_FILE));
/** Where the archive's tile data starts: a read at or past it is a tile block, not the header or the directory. */
const TILE_DATA_OFFSET = Number(new DataView(FIXTURE.buffer, FIXTURE.byteOffset).getBigUint64(56, true));
const PAGE = "/keyboard/map-tiles-harness.html";

interface Observed {
  ranges: { start: number; end: number }[];
  workerRequests: { url: string; status: number; type: string }[];
  /** Everything that went wrong on the page: script errors, console errors, failed or refused requests. */
  problems: string[];
}

async function observe(page: Page): Promise<Observed> {
  const seen: Observed = { ranges: [], workerRequests: [], problems: [] };
  page.on("pageerror", (error) => seen.problems.push(`page error: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") seen.problems.push(`console error: ${message.text()}`);
  });
  page.on("requestfailed", (request) =>
    seen.problems.push(`request failed: ${request.url()} (${request.failure()?.errorText})`),
  );
  page.on("response", async (response) => {
    const url = response.url();
    const type = (await response.headerValue("content-type")) ?? "";
    // The worker may be a page's, a module's or the library's own default location: any file by its name.
    if (/maplibre-gl-worker/.test(url)) seen.workerRequests.push({ url, status: response.status(), type });
    if (response.status() >= 400) seen.problems.push(`HTTP ${response.status()}: ${url}`);
  });

  // The archive, as a ranged route answers it.
  await page.route("**/fixture/map-tiles.pmtiles", async (route) => {
    const range = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers()["range"] ?? "");
    const common = { "accept-ranges": "bytes", etag: '"gg6-fixture"', "content-type": "application/octet-stream" };
    if (!range) {
      await route.fulfill({ status: 200, headers: common, body: Buffer.from(FIXTURE) });
      return;
    }
    const start = Number(range[1]);
    const end = Math.min(range[2] === "" ? FIXTURE.length - 1 : Number(range[2]), FIXTURE.length - 1);
    if (start >= FIXTURE.length) {
      // What a real server answers for a range past the end; the reader's own retry depends on the form.
      await route.fulfill({ status: 416, headers: { ...common, "content-range": `bytes */${FIXTURE.length}` } });
      return;
    }
    seen.ranges.push({ start, end });
    await route.fulfill({
      status: 206,
      headers: { ...common, "content-range": `bytes ${start}-${end}/${FIXTURE.length}` },
      body: Buffer.from(FIXTURE.subarray(start, end + 1)),
    });
  });
  // The Glass probes for label glyphs; the workspace's web server answers an unknown path with its own page.
  await page.route("**/fonts/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>Glass</title>" }),
  );
  return seen;
}

function atLeast(version: string | undefined, floor: string): boolean {
  const parse = (v: string) => v.split("-")[0]!.split(".").map(Number);
  const [have, want] = [parse(version ?? "0"), parse(floor)];
  for (let i = 0; i < 3; i++) {
    if ((have[i] ?? 0) !== (want[i] ?? 0)) return (have[i] ?? 0) > (want[i] ?? 0);
  }
  return true;
}

/** The canvas's colour at each sample, from a Playwright screenshot of the element (the drawing buffer
 * of a WebGL canvas is cleared once presented, so it cannot be read back; `live/basemap.spec.ts` has the
 * note). `null` for a sample outside the canvas. */
async function coloursAtSamples(page: Page): Promise<Record<keyof typeof SAMPLES, string | null>> {
  const points = await page.evaluate((samples) => {
    const map = window.__MAP__!;
    const out: Record<string, { x: number; y: number }> = {};
    for (const [name, at] of Object.entries(samples)) {
      const p = map.project([at.lon, at.lat]);
      out[name] = { x: Math.round(p.x), y: Math.round(p.y) };
    }
    return out;
  }, SAMPLES);
  const shot = await page.locator("canvas.maplibregl-canvas").screenshot();
  return page.evaluate(
    async ({ base64, points }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${base64}`;
      await image.decode();
      const scratch = document.createElement("canvas");
      scratch.width = image.naturalWidth;
      scratch.height = image.naturalHeight;
      const context = scratch.getContext("2d")!;
      context.drawImage(image, 0, 0);
      const out: Record<string, string | null> = {};
      for (const [name, at] of Object.entries(points)) {
        const inside = at.x >= 0 && at.y >= 0 && at.x < image.naturalWidth && at.y < image.naturalHeight;
        const d = inside ? context.getImageData(at.x, at.y, 1, 1).data : null;
        out[name] = d ? `${d[0]},${d[1]},${d[2]}` : null;
      }
      return out;
    },
    { base64: shot.toString("base64"), points },
  ) as Promise<Record<keyof typeof SAMPLES, string | null>>;
}

test("the committed fixture is what its script writes", () => {
  // A hand-edited or stale archive would be a different dataset from the one the script documents.
  expect(Buffer.from(FIXTURE).equals(Buffer.from(buildMapTilesFixture()))).toBe(true);
});

test("the Map view draws a vector basemap read through pmtiles:// on maplibre-gl 6.4.1 or later", async ({ page }) => {
  const seen = await observe(page);
  await page.goto(PAGE);

  // 1. The MapLibre the page is running, read from the page. Soft, so the assertions below still run
  //    (and show what they do) on a page that is not yet on 6.x.
  await expect.poll(() => page.evaluate(() => window.__MAPLIBRE_VERSION__)).toBeTruthy();
  const version = await page.evaluate(() => window.__MAPLIBRE_VERSION__);
  expect
    .soft(atLeast(version, "6.4.1"), `the page runs maplibre-gl ${version}, below 6.4.1 (CVE-2026-85061 is fixed from 6.4.1)`)
    .toBe(true);

  // 2. The protocol read a tile block, not only the header and the root directory. The reader always
  //    asks for the header (the first 16 KiB, which holds the root directory); only a tile that exists
  //    under the view makes it read a block of tile data.
  await expect
    .poll(() => seen.ranges.filter((r) => r.start >= TILE_DATA_OFFSET).length, {
      message:
        "only the header and root directory were read from the archive: no tile block was ever " +
        "asked for, so nothing under the view was drawn from it",
      timeout: 20_000,
    })
    .toBeGreaterThan(0);

  // 3. The canvas has map on it where the fixture draws: the water, the land cover and the bare ground
  //    between are three different colours. (A mounted but empty MapLibre is one flat colour.)
  await expect.poll(() => page.evaluate(() => window.__MAP__?.loaded() ?? false), { timeout: 20_000 }).toBe(true);
  await expect
    .poll(
      async () => {
        const c = await coloursAtSamples(page);
        return {
          allInside: Object.values(c).every((v) => v !== null),
          waterIsNotBare: c.water !== c.bare,
          landcoverIsNotBare: c.landcover !== c.bare,
          waterIsNotLandcover: c.water !== c.landcover,
        };
      },
      {
        message:
          "the canvas is not three colours where the fixture draws water, land cover and bare ground: " +
          "it mounted, or even read tiles, but drew none of them",
        timeout: 20_000,
      },
    )
    .toEqual({ allInside: true, waterIsNotBare: true, landcoverIsNotBare: true, waterIsNotLandcover: true });

  // 4. The worker. On 6.x the Glass serves its own (ADR-014 Amendment 2): it was asked for, answered
  //    and is not a page; and nothing on the page failed or raised an error.
  if (atLeast(version, "6.0.0")) {
    expect(seen.workerRequests, "no request for the MapLibre worker file was made").not.toEqual([]);
  }
  for (const worker of seen.workerRequests) {
    expect(worker.status, `the worker request ${worker.url} was refused`).toBeLessThan(400);
    expect(worker.type, `the worker request ${worker.url} was answered with a page, not a script`).not.toContain("text/html");
  }
  expect(seen.problems).toEqual([]);
});

test("where WebGL 2 is missing the Map view says so, not a blank panel", async ({ page }) => {
  // MapLibre 6 dropped WebGL 1; its `Map` throws `GPUInitializationError` without WebGL 2 (6.0.0 release
  // notes). Sigma, which draws the graph over the map, still runs on WebGL 1, so the page keeps that.
  await page.addInitScript(() => {
    for (const proto of [HTMLCanvasElement.prototype, OffscreenCanvas.prototype] as {
      getContext: (type: string, ...rest: unknown[]) => unknown;
    }[]) {
      const original = proto.getContext;
      proto.getContext = function (type: string, ...rest: unknown[]) {
        return type === "webgl2" ? null : original.call(this, type, ...rest);
      };
    }
  });
  await observe(page);
  await page.goto(PAGE);
  const alert = page.getByRole("alert");
  await expect(alert, "the Map view shows no message: a blank panel where the map should be").toContainText("WebGL 2", {
    timeout: 20_000,
  });
  // Words that say what to do, not a stack trace.
  await expect(alert).toContainText("browser");
  await expect(alert).not.toContainText("GPUInitializationError");
});
