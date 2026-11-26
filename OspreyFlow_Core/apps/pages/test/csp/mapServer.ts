// The strict-policy run's own server (slice GG5a): a test-only page that mounts MapLibre under the page service's real security
// policy. It is never a product route and never registered with the page registry: it lives under `test/` and is started by
// `map.spec.ts` on a free port of the test's own loopback.
//
// What is the real thing, called rather than copied:
//   * the policy: `securityHeaders()` from `server/headers.ts`, mounted with `app.use` first, as `server/app.ts:223` mounts it,
//     so every response here (the page, the assets, the worker, the style, the tiles) carries the builder's own policy;
//   * the assets: `assetsHandler()` from `server/assets.ts` at `ASSETS_PREFIX`, after the headers, as `server/app.ts:227` mounts
//     it, so the page's module, its stylesheet and MapLibre's worker are served with the types, names and refusals a deployed
//     page service gives them (a content-hashed name, and `.js`, because the handler has no type for `.mjs`);
//   * the worker: MapLibre's own `dist/maplibre-gl-worker.mjs`, byte for byte, named by `setWorkerUrl` on the page's own origin,
//     as `apps/workspace/src/map/maplibreWorker.ts` names it;
//   * the tiles: GG6's synthetic archive, `apps/workspace/keyboard/fixtures/map-tiles.pmtiles`, read from disk by path (the
//     owner's ruling, GG5a draft question 5 (a): a file read, not an import, so invariant I5's import boundary is untouched),
//     answered as a ranged route answers it (206 with `Content-Range`, 416 past the end).
//
// What is synthetic, and made here: the style, a raster tile and a sprite (single-colour PNGs), and a glyph range (a valid
// protobuf with the font stack and no glyphs). Their colours are the design tokens' own, read from `packages/design/tokens.css`
// by name. No real map data, style, tile or font of any kind (rule 9; ADR-152 decision 5: tiles, glyphs and sprites are
// same-origin).
//
// A second server, "elsewhere", is another origin on the same loopback (another port is another origin). A planted style or
// worker address points at it, and it records every request that reaches it: a request it records is one that left the page's
// origin, whatever the browser's own events said.
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";
import type { Server } from "node:http";

import { build } from "esbuild";
import express from "express";
import type { RequestHandler } from "express";

import { ASSETS_PREFIX, assetsHandler } from "../../server/assets.js";
import { securityHeaders } from "../../server/headers.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGES = resolve(HERE, "..", "..");
const CORE = resolve(PAGES, "..", "..");

/** GG6's archive (slice GG6, `mapTilesFixture.ts` writes it), read by path. */
export const ARCHIVE_FILE = join(CORE, "apps", "workspace", "keyboard", "fixtures", "map-tiles.pmtiles");
const MAPLIBRE_DIST = join(PAGES, "node_modules", "maplibre-gl", "dist");
const MAPLIBRE_DIST_HOISTED = join(CORE, "node_modules", "maplibre-gl", "dist");
const TOKENS = join(CORE, "packages", "design", "tokens.css");

/** The font stack the synthetic style names, and the glyph range it asks for. */
export const FONT_STACK = "Synthetic Sans";

// ---------------------------------------------------------------------------------------------------------------- the cases

/** Which style the page is given. Every one but `full` is a planted fault (rule 15), each the shape a real style file takes. */
export type StyleCase = "full" | "tile-elsewhere" | "glyphs-elsewhere" | "sprite-elsewhere" | "raster-elsewhere";
/** Where the page's worker is: the page's own origin (as `maplibreWorker.ts` does), or another origin (a planted fault). */
export type WorkerCase = "self" | "elsewhere";
/** How the archive is answered: by range (as the Conduit's ranged route answers it), or whole, ignoring `Range`. */
export type ArchiveCase = "ranged" | "whole";

/** A change to the policy the builder made, applied to its own output on its way out: the planted faults' only way in. */
export type PolicyPlant = (builderPolicy: string, origins: { self: string; elsewhere: string }) => string;

export interface PageRequest {
  /** The style, the worker and the archive's answer for this page. */
  style: StyleCase;
  worker: WorkerCase;
  archive: ArchiveCase;
  /** A planted change to the policy, if any (rule 15). */
  plant?: PolicyPlant;
}

export interface Served {
  method: string;
  path: string;
  range?: string;
  status: number;
}

export interface MapServer {
  origin: string;
  elsewhere: string;
  /** The page's address for a request; the server remembers what it was asked for under a key in the address. */
  pageUrl(request: PageRequest): string;
  /** Every request this origin answered, in order. */
  served: Served[];
  /** Every request that reached the other origin, in order: each one left the page's own origin. */
  reachedElsewhere: Served[];
  /** For each page served, the policy the builder made for it and the policy that went out (they differ only under a plant). */
  policies: { builder: string; sent: string }[];
  /** The offset in the archive at which tile data starts: a read at or past it is a tile, not the header or the directory. */
  tileDataOffset: number;
  close(): Promise<void>;
}

// -------------------------------------------------------------------------------------------------------- synthetic bytes

/** A design token's colour, by name, from `tokens.css` (its first, default-theme value). */
export function tokenColour(name: string): string {
  const match = new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6})\\b`).exec(readFileSync(TOKENS, "utf8"));
  if (!match) throw new Error(`tokens.css names no colour --${name}`);
  return match[1]!.toLowerCase();
}

/** The colours the synthetic style draws with, all tokens. */
export const COLOURS = {
  background: tokenColour("brass-ink"),
  raster: tokenColour("ch-ochre"),
  water: tokenColour("ch-azure"),
  landcover: tokenColour("ch-moss"),
  road: tokenColour("brass"),
} as const;
/** The raster layer's opacity: the background shows through it, so its pixels are a blend no other layer makes. */
export const RASTER_OPACITY = 0.5;

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(bytes: Buffer): number {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}
/** A single-colour, opaque RGBA PNG. */
export function solidPng(width: number, height: number, hex: string): Buffer {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.set([8, 6, 0, 0, 0], 8); // 8 bits, RGBA, deflate, no filter method beyond 0, not interlaced
  const row = Buffer.alloc(1 + width * 4);
  for (let x = 0; x < width; x++) row.set([r, g, b, 255], 1 + x * 4);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** A glyph range as MapLibre's glyph protobuf has it (`glyphs { fontstack { name, range } }`), holding no glyphs. */
function emptyGlyphRange(stack: string, range: string): Buffer {
  const field = (num: number, bytes: Buffer) => Buffer.concat([Buffer.from([(num << 3) | 2, bytes.length]), bytes]);
  return field(1, Buffer.concat([field(1, Buffer.from(stack, "utf8")), field(2, Buffer.from(range, "ascii"))]));
}

/** The archive's own centre (PMTiles v3 header: longitude and latitude times 1e7 at bytes 119 and 123, centre zoom at 118). */
function archiveCentre(archive: Buffer): { lon: number; lat: number; zoom: number } {
  return { zoom: archive.readUInt8(118), lon: archive.readInt32LE(119) / 1e7, lat: archive.readInt32LE(123) / 1e7 };
}

function styleFor(kind: StyleCase, self: string, elsewhere: string, archive: Buffer): object {
  const centre = archiveCentre(archive);
  const at = (base: string, path: string) => `${base}${path}`;
  const glyphsBase = kind === "glyphs-elsewhere" ? elsewhere : self;
  const spriteBase = kind === "sprite-elsewhere" ? elsewhere : self;
  const rasterBase = kind === "raster-elsewhere" ? elsewhere : self;
  const sources: Record<string, object> = {
    basemap: { type: "vector", url: `pmtiles://${at(self, "/fixture/map-tiles.pmtiles")}` },
    raster: { type: "raster", tiles: [at(rasterBase, "/fixture/raster/{z}/{x}/{y}.png")], tileSize: 256 },
    places: {
      type: "geojson",
      data: { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [centre.lon, centre.lat] } }] },
    },
  };
  const layers: object[] = [
    { id: "background", type: "background", paint: { "background-color": COLOURS.background } },
    { id: "raster", type: "raster", source: "raster", paint: { "raster-opacity": RASTER_OPACITY, "raster-fade-duration": 0 } },
    { id: "water", type: "fill", source: "basemap", "source-layer": "water", paint: { "fill-color": COLOURS.water, "fill-antialias": false } },
    { id: "landcover", type: "fill", source: "basemap", "source-layer": "landcover", paint: { "fill-color": COLOURS.landcover, "fill-antialias": false } },
    { id: "road", type: "line", source: "basemap", "source-layer": "transportation", paint: { "line-color": COLOURS.road, "line-width": 3 } },
    {
      id: "road-label",
      type: "symbol",
      source: "basemap",
      "source-layer": "transportation",
      layout: { "text-field": "Synthetic road", "text-font": [FONT_STACK], "symbol-placement": "line" },
    },
    { id: "place", type: "symbol", source: "places", layout: { "icon-image": "dot", "icon-allow-overlap": true } },
  ];
  if (kind === "tile-elsewhere") {
    // A vector source as a real style file names one: a `tiles` template on another origin (fetched in the worker).
    sources["elsewhere"] = { type: "vector", tiles: [at(elsewhere, "/tiles/{z}/{x}/{y}.pbf")], maxzoom: 14 };
    layers.push({ id: "elsewhere-water", type: "fill", source: "elsewhere", "source-layer": "water", paint: { "fill-color": COLOURS.water } });
  }
  return {
    version: 8,
    name: "GG5a synthetic style (test only)",
    center: [centre.lon, centre.lat],
    zoom: centre.zoom + 1,
    glyphs: at(glyphsBase, "/fixture/glyphs/{fontstack}/{range}.pbf"),
    sprite: at(spriteBase, "/fixture/sprite"),
    sources,
    layers,
  };
}

// -------------------------------------------------------------------------------------------------------------- the assets

function hashedName(stem: string, bytes: Buffer, ext: string): string {
  return `${stem}-${createHash("sha256").update(bytes).digest("hex").slice(0, 8).toUpperCase()}${ext}`;
}

interface Assets {
  dir: string;
  module: string;
  stylesheet: string;
  worker: string;
  workerBytes: Buffer;
}

/** The page's module and stylesheet, bundled by this test's own esbuild call with the options `scripts/assets.mjs` gives a
 * module (one ES module, ES2018, browser, minified, no splitting, no source map), and MapLibre's worker file copied beside them. */
async function buildAssets(): Promise<Assets> {
  const dir = mkdtempSync(join(tmpdir(), "ospreyflow-pages-csp-assets-"));
  await build({
    entryPoints: [join(HERE, "page", "map-page.ts"), join(HERE, "page", "map-page.css")],
    outdir: dir,
    entryNames: "[name]-[hash]",
    bundle: true,
    format: "esm",
    target: "es2018",
    platform: "browser",
    minify: true,
    sourcemap: false,
    splitting: false,
    legalComments: "none",
    logLevel: "silent",
    absWorkingDir: PAGES,
    // `@import` of MapLibre's own stylesheet in `map-page.css` reads it from the package.
    nodePaths: [join(PAGES, "node_modules"), join(CORE, "node_modules")],
  });
  const names = readdirSync(dir);
  const module = names.find((n) => /^map-page-[A-Z0-9]{8}\.js$/.test(n));
  const stylesheet = names.find((n) => /^map-page-[A-Z0-9]{8}\.css$/.test(n));
  if (!module || !stylesheet) throw new Error(`the test page's assets were not built: ${names.join(", ")}`);
  // npm hoists the one 6.19.0 to the root `node_modules` (the workspace resolves the same version), so look there second.
  const distDir = existsSync(join(MAPLIBRE_DIST, "maplibre-gl-worker.mjs")) ? MAPLIBRE_DIST : MAPLIBRE_DIST_HOISTED;
  const workerBytes = readFileSync(join(distDir, "maplibre-gl-worker.mjs"));
  const worker = hashedName("maplibre-gl-worker", workerBytes, ".js");
  copyFileSync(join(distDir, "maplibre-gl-worker.mjs"), join(dir, worker));
  return { dir, module, stylesheet, worker, workerBytes };
}

// -------------------------------------------------------------------------------------------------------------- the servers

function listen(app: express.Express): Promise<{ server: Server; origin: string }> {
  return new Promise((done, fail) => {
    const server = app.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as AddressInfo;
      done({ server, origin: `http://127.0.0.1:${port}` });
    });
    server.on("error", fail);
  });
}

function close(server: Server): Promise<void> {
  return new Promise((done) => {
    server.closeAllConnections();
    server.close(() => done());
  });
}

function ranged(archive: Buffer, how: () => ArchiveCase): RequestHandler {
  return (req, res) => {
    const common = { "Accept-Ranges": "bytes", "Content-Type": "application/octet-stream", ETag: '"gg6-fixture"' };
    const range = /^bytes=(\d+)-(\d*)$/.exec(req.get("range") ?? "");
    if (how() === "whole" || !range) {
      // The planted fault: what a forwarder that carries no `Range` returns (the whole file, 200), as PL10's does today.
      res.status(200).set(common).send(archive);
      return;
    }
    const start = Number(range[1]);
    const end = Math.min(range[2] === "" ? archive.length - 1 : Number(range[2]), archive.length - 1);
    if (start >= archive.length) {
      res.status(416).set({ ...common, "Content-Range": `bytes */${archive.length}` }).end();
      return;
    }
    res
      .status(206)
      .set({ ...common, "Content-Range": `bytes ${start}-${end}/${archive.length}` })
      .send(archive.subarray(start, end + 1));
  };
}

export async function startMapServer(): Promise<MapServer> {
  const assets = await buildAssets();
  const archive = readFileSync(ARCHIVE_FILE);
  const tileDataOffset = Number(archive.readBigUInt64LE(56));
  const sprite = solidPng(16, 16, COLOURS.road);
  const raster = solidPng(256, 256, COLOURS.raster);
  const served: Served[] = [];
  const reachedElsewhere: Served[] = [];
  const policies: { builder: string; sent: string }[] = [];
  const requests = new Map<string, PageRequest>();
  let archiveCase: ArchiveCase = "ranged";
  let current: PageRequest | undefined;
  let origins = { self: "", elsewhere: "" };

  // ---- elsewhere: another origin, recording everything that reaches it, and answering it as a real tile host would.
  const other = express();
  other.disable("x-powered-by");
  other.use((req, res, next) => {
    res.on("finish", () => reachedElsewhere.push({ method: req.method, path: req.originalUrl, status: res.statusCode }));
    res.set("Access-Control-Allow-Origin", "*");
    next();
  });
  other.get(/.*/, (req, res) => {
    if (req.path.endsWith(".js")) res.type("text/javascript").send(assets.workerBytes);
    else if (req.path.endsWith(".png")) res.type("image/png").send(req.path.includes("sprite") ? sprite : raster);
    else if (req.path.endsWith(".json")) res.json({ dot: { x: 0, y: 0, width: 16, height: 16, pixelRatio: 1 } });
    else if (req.path.endsWith(".pbf")) res.type("application/x-protobuf").send(emptyGlyphRange(FONT_STACK, "0-255"));
    else res.status(404).end();
  });

  // ---- the page's own origin.
  const app = express();
  app.disable("x-powered-by");
  app.disable("etag");
  app.use((req, res, next) => {
    res.on("finish", () =>
      served.push({ method: req.method, path: req.originalUrl, ...(req.get("range") ? { range: req.get("range")! } : {}), status: res.statusCode }),
    );
    next();
  });
  // The real policy, first, as `server/app.ts:223` mounts it.
  app.use(securityHeaders());
  // A plant, if the page open now names one: applied to the builder's own output, after the builder, before anything is sent,
  // on every response while that page is open (the spec runs one page at a time). Every response, not only the page's: a
  // dedicated worker is governed by the policy on its own script's response, not by its page's (measured: with `connect-src`
  // widened on the page alone, both browsers still refuse the worker's outside tile under the worker's own policy).
  app.use((req, res, next) => {
    const key = typeof req.query["page"] === "string" ? req.query["page"] : undefined;
    if (req.path === "/map") current = key === undefined ? undefined : requests.get(key);
    const pageRequest = current;
    const builder = String(res.getHeader("Content-Security-Policy") ?? "");
    if (pageRequest?.plant) res.setHeader("Content-Security-Policy", pageRequest.plant(builder, origins));
    if (req.path === "/map") policies.push({ builder, sent: String(res.getHeader("Content-Security-Policy") ?? "") });
    next();
  });
  // The real assets handler, after the headers, as `server/app.ts:227` mounts it.
  app.use(ASSETS_PREFIX, assetsHandler(assets.dir));

  app.get("/map", (req, res) => {
    const key = String(req.query["page"] ?? "");
    const pageRequest = current;
    if (!pageRequest) {
      res.status(404).type("text/plain").send("no such page");
      return;
    }
    archiveCase = pageRequest.archive;
    const nonce = String(res.locals["cspNonce"]);
    const worker = pageRequest.worker === "self" ? `${ASSETS_PREFIX}/${assets.worker}` : `${origins.elsewhere}/assets/${assets.worker}`;
    const style = `/fixture/style.json?page=${encodeURIComponent(key)}`;
    const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    res.type("html").send(`<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>Map under the page service's policy (test page, GG5a)</title>
<meta name="map-worker" content="${escape(worker)}">
<meta name="map-style" content="${escape(style)}">
<link rel="stylesheet" href="${ASSETS_PREFIX}/${assets.stylesheet}">
<script type="module" src="${ASSETS_PREFIX}/${assets.module}" nonce="${escape(nonce)}"></script>
</head>
<body>
<main>
<h1>Map (test page)</h1>
<div id="map"></div>
</main>
</body>
</html>
`);
  });
  app.get("/fixture/style.json", (req, res) => {
    const pageRequest = requests.get(String(req.query["page"] ?? ""));
    if (!pageRequest) {
      res.status(404).end();
      return;
    }
    res.json(styleFor(pageRequest.style, origins.self, origins.elsewhere, archive));
  });
  app.get("/fixture/map-tiles.pmtiles", ranged(archive, () => archiveCase));
  app.get("/fixture/raster/:z/:x/:y.png", (_req, res) => res.type("image/png").send(raster));
  app.get("/fixture/sprite.json", (_req, res) => res.json({ dot: { x: 0, y: 0, width: 16, height: 16, pixelRatio: 1 } }));
  app.get("/fixture/sprite.png", (_req, res) => res.type("image/png").send(sprite));
  app.get("/fixture/glyphs/:stack/:range.pbf", (req, res) => {
    res.type("application/x-protobuf").send(emptyGlyphRange(String(req.params["stack"]), String(req.params["range"])));
  });

  const own = await listen(app);
  const elsewhere = await listen(other);
  origins = { self: own.origin, elsewhere: elsewhere.origin };
  let counter = 0;

  return {
    origin: own.origin,
    elsewhere: elsewhere.origin,
    served,
    reachedElsewhere,
    policies,
    tileDataOffset,
    pageUrl(request) {
      const key = `p${++counter}`;
      requests.set(key, request);
      return `${own.origin}/map?page=${key}`;
    },
    async close() {
      await Promise.all([close(own.server), close(elsewhere.server)]);
      rmSync(assets.dir, { recursive: true, force: true });
    },
  };
}
