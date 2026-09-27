// **Stage 3a's first residual, closed: the Glass renders tiles from a real local PMTiles build.**
//
// `07_BUILD_PLAN.md`'s Stage 3a disclosure named "the actual local PMTiles basemap build" as the
// thing that had never happened. Round 12 built one for real (Geofabrik's Rutland extract →
// planetiler → PMTiles → `register_local_provider` → `verify_map`; `docs/demo/2026-09-26/
// RUNBOOK.md` has the timings). This spec is the other half: proof that the artefact that build
// produced is one the Glass's Map view can actually draw, which no amount of checking the file
// on disk establishes.
//
// **Why not `make glass-map-verify`**, which round 12's brief named for this: that target runs
// `map-verify/contrast.spec.ts`, a `toHaveScreenshot()` comparison against `map-verify/
// showcase.tsx` — a static page with no Conduit, no PMTiles source and no MapLibre tile fetch.
// It is a real check of a real thing (the contrast floor over the basemap's chrome colours) and
// it stays; it simply cannot see a tile pipeline, so it could not have proven this.
//
// Three independent assertions, because each catches a failure the others miss:
//   1. the "Basemap not built" alert is absent — `basemapAvailability.ts`'s preflight got a
//      readable file rather than the route's named 404;
//   2. the Conduit really served ranged PMTiles reads — the `pmtiles://` protocol handler
//      fetching its own directory and tile blocks, which is what a working basemap *does*;
//   3. the canvas really has map on it — more than one distinct colour, so a blank-but-mounted
//      MapLibre (the exact silent failure the alert in (1) exists to replace) still fails here.
// (1) and (2) can both pass with nothing drawn; (3) is what makes this a render proof.
import { expect, test } from "@playwright/test";

import { apiBaseUrl, freshWorkspaceUrl, liveOnly } from "./live";

test.beforeEach(liveOnly);

test("the Map view draws tiles served from the real local PMTiles build", async ({
  page,
  request,
}) => {
  const rangedTileReads: { url: string; status: number }[] = [];
  // The distinct byte ranges asked for, which is the signal that separates "the basemap was
  // opened" from "the basemap was drawn". The pmtiles protocol always reads the header and the
  // root directory — two or three ranges — whatever the viewport shows. It only goes on to read
  // *tile block* ranges for tiles that actually exist under the current view. So a basemap whose
  // extract does not cover the data (see `GEOFABRIK_REGIONS`' own note: the HMP fixture is in
  // Berkshire, and a Rutland build is a valid file with nothing under the viewport) produces a
  // handful of ranges and stops, while a covering one produces many.
  const distinctRanges = new Set<string>();
  page.on("request", (tileRequest) => {
    if (tileRequest.url().includes("/v1/map/local-source/")) {
      const range = tileRequest.headers()["range"];
      if (range) distinctRanges.add(range);
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/v1/map/local-source/")) {
      rangedTileReads.push({ url: response.url(), status: response.status() });
    }
  });

  await page.goto(await freshWorkspaceUrl(request));
  await page.getByRole("button", { name: "Map" }).click();

  // 1. The named failure state is absent. Asserted by its own role and text, not by a screenshot,
  //    so the reason for a failure here is readable in the report rather than a pixel diff.
  await expect(
    page.getByRole("alert").filter({ hasText: "Basemap not built" }),
  ).toHaveCount(0);

  // The provider's own credit, which `00_ARCHITECTURE.md` §1.2 principle 3 requires travel with
  // the layer. Both halves: the tiles are a CC-BY OpenMapTiles work as well as ODbL OSM data —
  // planetiler's own closing output says so, and until round 12 only the OSM half was declared.
  await expect(
    page.getByText(/© OpenMapTiles © OpenStreetMap contributors/),
  ).toBeVisible();

  // 2. Real ranged reads reached the real route. The pmtiles protocol never downloads the file
  //    whole — it reads its header, then its directory, then individual tile blocks — so several
  //    partial responses are the signature of a source being read rather than merely existing.
  await expect
    .poll(() => rangedTileReads.filter((r) => r.status === 206).length, {
      message:
        `expected the pmtiles protocol to issue ranged reads against ${apiBaseUrl()}` +
        "/v1/map/local-source/… — none arrived, so nothing ever tried to read the basemap",
      timeout: 30_000,
    })
    .toBeGreaterThan(1);
  expect(
    rangedTileReads.every((r) => r.status === 200 || r.status === 206),
  ).toBe(true);

  // 3. The canvas has map drawn on it. A mounted-but-blank MapLibre canvas is a single flat
  //    colour; a rendered basemap is not. Sampling a grid of points off the canvas bitmap is the
  //    cheapest assertion that distinguishes them without a stored reference image — this is
  //    deliberately *not* a screenshot comparison, because the tiles' own content will change
  //    with every fresh Geofabrik extract and a baseline would have to be regenerated each time.
  // 3a. Tile *blocks* were read, not just the header and directory — the basemap's extract
  //     actually covers what the viewport is looking at.
  await expect
    .poll(() => distinctRanges.size, {
      message:
        "the pmtiles source was opened but only its header/directory ranges were ever read, so " +
        "no tile under the current viewport exists in it. The usual cause is not a broken " +
        "basemap but the wrong extract: the region built must cover the fixture's own " +
        "coordinates (the HMP yards are in Berkshire — scripts/build_local_basemap.py's " +
        "GEOFABRIK_REGIONS has the full note).",
      timeout: 30_000,
    })
    .toBeGreaterThan(3);

  // 3b. And the canvas really has map on it.
  //
  // Via Playwright's own screenshot of the element, decoded back inside the page — *not* by
  // reading the canvas directly, which was the first thing tried and does not work here.
  // MapLibre creates its WebGL context with the default `preserveDrawingBuffer: false`, so by
  // the time a `drawImage` from it runs the drawing buffer has already been presented and
  // cleared: it reads back as a single flat colour whether the map drew anything or not, which
  // makes it useless for exactly the question being asked. A Playwright screenshot captures the
  // composited frame instead, so it sees what a person would.
  const canvas = page.locator("canvas.maplibregl-canvas");
  await expect(canvas).toBeVisible();
  const screenshot = await canvas.screenshot();
  const distinctColours = await page.evaluate(async (base64: string) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const scratch = document.createElement("canvas");
    scratch.width = image.naturalWidth;
    scratch.height = image.naturalHeight;
    const context = scratch.getContext("2d");
    if (!context) return 0;
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, scratch.width, scratch.height);
    const seen = new Set<string>();
    // A coarse stride: this is asking "is there more than one colour here", not measuring the
    // palette, and sampling every pixel of a retina-sized canvas is needless work.
    for (let i = 0; i < data.length; i += 4 * 97) {
      seen.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
    }
    return seen.size;
  }, screenshot.toString("base64"));
  expect(
    distinctColours,
    "the MapLibre canvas is a single flat colour — it mounted but drew no tiles, which is the " +
      "silent blank-canvas failure the 'Basemap not built' alert was added to replace",
  ).toBeGreaterThan(1);
});
