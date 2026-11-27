// The strict-policy run (slice GG5a; ADR-152 decision 8): MapLibre 6.19 under the page service's own security policy, in a real
// browser (Chromium and WebKit: the owner's ruling on GG5a's draft, question 2 (a)), and the standing test that no map request
// leaves the deployment.
//
// The page is test-only (`mapServer.ts` has what is real and what is synthetic). For each page this records
//   (a) every `securitypolicyviolation` event, in the document and in every worker the page starts (a request a worker makes
//       is refused in the worker, and the document never hears of it);
//   (b) every request whose origin is not the page's own: seen by the browser (its request events and a route that refuses
//       anything bound for a third origin), and, independently, every request that reached the other origin's own server;
//   (c) the map reaching `load` and `idle`, a tile block read from the archive, and the canvas showing the water and land cover
//       drawn from it and the raster tile drawn under them, each in its own token colour.
// No refusal is excused: nothing the test does may be refused by the policy, so every one it records is the page's.
// `failures()` turns a record into the list of what is wrong. The page under the real policy must have none. Every planted fault
// below (rule 15: each the shape the page really sends or receives at its own call site) runs through the same `failures()`
// and must be named by it: a check is not believed until it has been shown red.
//
//   npm run test:csp --workspace apps/pages        (its CI job is `ci-wiring.patch` beside this file, for the owner to apply)
import { inflateSync } from "node:zlib";

import { expect, test } from "@playwright/test";
import type { Page, Worker } from "@playwright/test";

import { COLOURS, RASTER_OPACITY, THIRD_ORIGIN, startMapServer } from "./mapServer.js";
import type { MapServer, PageRequest, PolicyPlant, Served } from "./mapServer.js";

interface Violation {
  where: "document" | "worker";
  directive: string;
  blocked: string;
  source: string;
  line: number;
}

interface Run {
  browser: string;
  violations: Violation[];
  /** CSP refusals the browser wrote to the console (a second witness to (a)). */
  consoleRefusals: string[];
  /** Requests the browser made to an origin not the page's own. */
  outside: string[];
  /** Requests that reached the other origin's server. */
  reachedElsewhere: string[];
  loaded: boolean;
  idle: boolean;
  version: string;
  mapErrors: string[];
  pageErrors: string[];
  tileReads: number;
  drawn: { water: number; landcover: number; raster: number };
  policy: { builder: string; sent: string; received: string };
  /** The policy on each response that served the worker file, as the builder made it and as it went out. */
  workerPolicies: { builder: string; sent: string }[];
  workers: string[];
  /** Every request the page's own origin answered for this page. */
  served: Served[];
}

/** How long a map is given to reach `idle`, and then to show every layer. A planted fault that stops the map waits this out. */
const READY_MS = 12_000;
const DRAWN_MS = 6_000;

let server: MapServer;
test.beforeAll(async () => {
  server = await startMapServer();
});
test.afterAll(async () => {
  await server?.close();
});

// ------------------------------------------------------------------------------------------------------------ recording

/** What these functions reach in the browser (the document or a worker), typed here: this folder's Node `tsconfig` has no DOM
 * library, and the page's own types live with the page (`page/map-page.ts`, which has its own). */
interface InBrowser {
  __CSP__?: unknown[];
  __MAP_STATE__?: { version: string; loaded: boolean; idle: boolean; errors: string[] };
  __MAP__?: { once(event: "render", listener: () => void): unknown; triggerRepaint(): void; getCanvas(): { toDataURL(type: "image/png"): string } };
  addEventListener(
    type: "securitypolicyviolation",
    listener: (e: { effectiveDirective: string; violatedDirective: string; blockedURI: string; sourceFile: string; lineNumber: number }) => void,
  ): void;
}

/** Installed in the document before any of its own script runs, and in each worker as soon as it is seen. */
function recordViolations(where: string): void {
  const scope = globalThis as unknown as InBrowser;
  if (scope.__CSP__) return;
  const seen: unknown[] = [];
  scope.__CSP__ = seen;
  scope.addEventListener("securitypolicyviolation", (e) => {
    seen.push({ where, directive: e.effectiveDirective || e.violatedDirective, blocked: e.blockedURI, source: e.sourceFile, line: e.lineNumber });
  });
}

function originOf(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

/** A request that is not a network request (a `data:` URL, or a `blob:` URL the page made itself) has not left anything. */
function isNetwork(url: string): boolean {
  return !url.startsWith("data:") && !url.startsWith("blob:") && !url.startsWith("about:");
}

/** `whileDrawing` is a plant's way to make the page do something while the picture is being read. */
async function openMap(page: Page, browser: string, request: PageRequest, whileDrawing?: () => Promise<void>): Promise<Run> {
  const servedBefore = server.served.length;
  const elsewhereBefore = server.reachedElsewhere.length;
  const policiesBefore = server.policies.length;
  const workerPoliciesBefore = server.workerPolicies.length;
  const outside: string[] = [];
  const consoleRefusals: string[] = [];
  const pageErrors: string[] = [];
  const workers: Worker[] = [];

  await page.addInitScript(recordViolations, "document");
  let phase = "load";
  const refusal = (where: string) => (message: { text(): string }) => {
    if (/content security policy|refused to/i.test(message.text())) consoleRefusals.push(`[${phase}, ${where}] ${message.text()}`);
  };
  page.on("worker", (worker) => {
    workers.push(worker);
    worker.on("console", refusal("worker"));
    void worker.evaluate(recordViolations, "worker").catch(() => undefined);
  });
  page.on("request", (req) => {
    if (isNetwork(req.url()) && originOf(req.url()) !== server.origin) outside.push(req.url());
  });
  page.on("console", refusal("document"));
  page.on("pageerror", (error) => pageErrors.push(error.message));
  // Nothing may reach a third origin from this test, whatever a plant asks for: the other origin is the only one let through,
  // and only so that its own server can witness the request (b).
  await page.context().route(
    (url) => isNetwork(url.href) && url.origin !== server.origin,
    async (route) => {
      const url = route.request().url();
      if (!outside.includes(url)) outside.push(url);
      if (originOf(url) === server.elsewhere) await route.continue();
      else await route.abort("blockedbyclient");
    },
  );

  const response = await page.goto(server.pageUrl(request));
  const received = (await response?.headerValue("content-security-policy")) ?? "";
  await page
    .waitForFunction(() => (globalThis as unknown as InBrowser).__MAP_STATE__?.idle === true, undefined, { timeout: READY_MS })
    .catch(() => undefined);
  // Late reports: a worker's refusal or the last tile's error event.
  await page.waitForTimeout(750);

  const state = await page.evaluate(() => {
    const scope = globalThis as unknown as InBrowser;
    return {
      version: scope.__MAP_STATE__?.version ?? "",
      loaded: scope.__MAP_STATE__?.loaded ?? false,
      idle: scope.__MAP_STATE__?.idle ?? false,
      errors: scope.__MAP_STATE__?.errors ?? [],
    };
  });
  // The picture, read until every layer shows or the time is up, as GG6's spec also polls.
  phase = "drawing";
  await whileDrawing?.();
  let drawn = { water: 0, landcover: 0, raster: 0 };
  if (state.idle) {
    const until = Date.now() + DRAWN_MS;
    do {
      drawn = await coloursDrawn(page);
      if (drawn.water >= DRAWN && drawn.landcover >= DRAWN && drawn.raster >= DRAWN) break;
      await page.waitForTimeout(250);
    } while (Date.now() < until);
  }
  await page.waitForTimeout(250);
  // (a), read last: every event up to here, those fired while the picture was read among them.
  const violations = (await page.evaluate(() => (globalThis as unknown as InBrowser).__CSP__ ?? [])) as Violation[];
  for (const worker of workers) {
    const inWorker = await worker
      .evaluate(() => (globalThis as unknown as InBrowser).__CSP__ ?? [])
      .catch(() => [] as unknown[]);
    violations.push(...(inWorker as Violation[]));
  }
  const policy = server.policies[policiesBefore] ?? { builder: "", sent: "" };
  return {
    browser,
    violations,
    consoleRefusals,
    outside,
    reachedElsewhere: server.reachedElsewhere.slice(elsewhereBefore).map((r) => `${server.elsewhere}${r.path}`),
    loaded: state.loaded,
    idle: state.idle,
    version: state.version,
    mapErrors: state.errors,
    pageErrors,
    tileReads: server.served
      .slice(servedBefore)
      .filter((s) => s.path.startsWith("/fixture/map-tiles.pmtiles") && s.status === 206 && Number(/^bytes=(\d+)/.exec(s.range ?? "")?.[1]) >= server.tileDataOffset)
      .length,
    drawn,
    policy: { ...policy, received },
    workerPolicies: server.workerPolicies.slice(workerPoliciesBefore),
    workers: workers.map((w) => w.url()),
    served: server.served.slice(servedBefore),
  };
}

// ---------------------------------------------------------------------------------------------------------- the picture

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}

/** An 8-bit RGB or RGBA PNG, as a canvas writes one, decoded to RGBA (no interlacing; filters 0 to 4). */
function decodePng(png: Buffer): { width: number; height: number; rgba: Uint8Array } {
  let at = 8;
  let width = 0;
  let height = 0;
  let channels = 4;
  const data: Buffer[] = [];
  while (at < png.length) {
    const length = png.readUInt32BE(at);
    const type = png.toString("ascii", at + 4, at + 8);
    const body = png.subarray(at + 8, at + 8 + length);
    if (type === "IHDR") {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      channels = body[9] === 6 ? 4 : 3;
      if (body[8] !== 8 || (body[9] !== 6 && body[9] !== 2) || body[12] !== 0) throw new Error("not an 8-bit RGB(A) PNG");
    }
    if (type === "IDAT") data.push(body);
    at += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(data));
  const stride = width * channels;
  const out = new Uint8Array(width * height * 4);
  const previous = new Uint8Array(stride);
  const current = new Uint8Array(stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)]!;
    for (let x = 0; x < stride; x++) {
      const value = raw[y * (stride + 1) + 1 + x]!;
      const left = x >= channels ? current[x - channels]! : 0;
      const up = previous[x]!;
      const upLeft = x >= channels ? previous[x - channels]! : 0;
      let predicted = 0;
      if (filter === 1) predicted = left;
      else if (filter === 2) predicted = up;
      else if (filter === 3) predicted = (left + up) >> 1;
      else if (filter === 4) {
        const p = left + up - upLeft;
        const [pa, pb, pc] = [Math.abs(p - left), Math.abs(p - up), Math.abs(p - upLeft)];
        predicted = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
      }
      current[x] = (value + predicted) & 0xff;
    }
    for (let x = 0; x < width; x++) {
      out.set([current[x * channels]!, current[x * channels + 1]!, current[x * channels + 2]!, 255], (y * width + x) * 4);
    }
    previous.set(current);
  }
  return { width, height, rgba: out };
}

/** How many of the canvas's pixels are each layer's own colour: the water and the land cover (opaque fills from the archive's
 * tiles), and the raster tile at its opacity over the background (a blend no other layer makes). A mounted map that drew no
 * tile is the background alone. The map is asked for one more frame and its canvas is read inside that frame's `render`
 * event, because a WebGL canvas's drawing buffer is cleared once presented. Not a screenshot: in WebKit, Playwright's adds a
 * `<style>` element to the page, which the page's policy refuses (measured: a `style-src-elem` event and a console line), and a
 * test the policy refuses would have to excuse a refusal. */
async function coloursDrawn(page: Page): Promise<{ water: number; landcover: number; raster: number }> {
  const url = await page.evaluate(
    () =>
      new Promise<string>((done) => {
        const map = (globalThis as unknown as InBrowser).__MAP__!;
        map.once("render", () => done(map.getCanvas().toDataURL("image/png")));
        map.triggerRepaint();
      }),
  );
  const shot = decodePng(Buffer.from(url.slice(url.indexOf(",") + 1), "base64"));
  const background = rgb(COLOURS.background);
  const rasterColour = rgb(COLOURS.raster);
  const targets = {
    water: rgb(COLOURS.water),
    landcover: rgb(COLOURS.landcover),
    raster: rasterColour.map((c, i) => Math.round(c * RASTER_OPACITY + background[i]! * (1 - RASTER_OPACITY))) as [number, number, number],
  };
  const counts = { water: 0, landcover: 0, raster: 0 };
  for (let i = 0; i < shot.rgba.length; i += 4) {
    for (const [name, [r, g, b]] of Object.entries(targets) as [keyof typeof counts, [number, number, number]][]) {
      if (Math.abs(shot.rgba[i]! - r) <= 3 && Math.abs(shot.rgba[i + 1]! - g) <= 3 && Math.abs(shot.rgba[i + 2]! - b) <= 3) counts[name]++;
    }
  }
  return counts;
}

// ------------------------------------------------------------------------------------------------------------ the verdict

/** Enough pixels of a colour to be a drawn tile and not an edge's antialiasing. */
const DRAWN = 200;

/** Everything wrong with a run, in words. Empty for a map that drew under the policy and asked nothing of another origin. */
function failures(run: Run): string[] {
  const out: string[] = [];
  for (const v of run.violations) out.push(`policy violation: ${v.directive} refused ${v.blocked || "(no address)"} in the ${v.where}`);
  for (const text of run.consoleRefusals) out.push(`refused, on the console: ${text}`);
  for (const url of new Set([...run.outside, ...run.reachedElsewhere])) out.push(`request to another origin: ${url}`);
  // None sent and none made are equal, so a page that never passed the headers is named for itself.
  if (!run.policy.builder) out.push("the page was served with no policy");
  else if (run.policy.received !== run.policy.builder) out.push(`the policy sent is not the builder's own: ${run.policy.received}`);
  // A dedicated worker obeys the policy on its own script's response, not its page's (measured: the "page alone" case below).
  for (const w of run.workerPolicies) {
    if (!w.builder) out.push("the worker's script was served with no policy");
    else if (w.sent !== w.builder) out.push(`the worker's policy is not the builder's own: ${w.sent}`);
  }
  if (!run.loaded) out.push("the map never reached load");
  if (!run.idle) out.push("the map never reached idle");
  if (run.tileReads === 0) out.push("no tile block was read from the archive");
  if (run.drawn.water < DRAWN) out.push(`no water drawn from the archive's tiles (${run.drawn.water} pixels)`);
  if (run.drawn.landcover < DRAWN) out.push(`no land cover drawn from the archive's tiles (${run.drawn.landcover} pixels)`);
  if (run.drawn.raster < DRAWN) out.push(`no raster tile drawn (${run.drawn.raster} pixels)`);
  for (const e of run.mapErrors) out.push(`map error: ${e}`);
  for (const e of run.pageErrors) out.push(`page error: ${e}`);
  return out;
}

// --------------------------------------------------------------------------------------------------------- the plants

const directives = (policy: string) => policy.split(";").map((d) => d.trim()).filter(Boolean);
const nameOf = (directive: string) => directive.split(/\s+/)[0]!;

/** The builder's policy with one directive's value replaced (or added). */
const setDirective =
  (name: string, value: string): PolicyPlant =>
  (policy) => {
    const kept = directives(policy).filter((d) => nameOf(d) !== name);
    return [...kept, `${name} ${value}`].join(";");
  };
/** The builder's policy with one directive taken out. */
const dropDirective =
  (name: string): PolicyPlant =>
  (policy) =>
    directives(policy)
      .filter((d) => nameOf(d) !== name)
      .join(";");

const FULL: PageRequest = { style: "full", worker: "self", archive: "ranged" };

function show(run: Run): string {
  return JSON.stringify({ ...run, served: run.served.length, policy: { builder: run.policy.builder.replace(/nonce-[^']+/g, "nonce-N") } }, null, 1);
}

/** One line per case for the run's own log, which the report's directive table is read from (and a verifier checks it against). */
function record(caseName: string, run: Run): void {
  const lines = [...new Set(failures(run).map((f) => f.replace(/nonce-[^']+/g, "nonce-N")))];
  console.log(`RECORD [${run.browser}] ${caseName}: ${JSON.stringify({ failures: lines, drawn: run.drawn, tileReads: run.tileReads, workers: run.workers.length })}`);
}

/** The directives the violations name, `-elem` and `-attr` folded into the directive they refine. */
function directivesRefused(run: Run): string[] {
  return [...new Set(run.violations.map((v) => v.directive.replace(/-(elem|attr)$/, "")))].sort();
}

const elsewherePath = (path: string) => new RegExp(`^request to another origin: ${server.elsewhere.replace(/[.]/g, "\\.")}${path}`);
const refusedElsewhere = (directive: string, path: string, where: "document" | "worker") =>
  new RegExp(`^policy violation: ${directive} refused ${server.elsewhere.replace(/[.]/g, "\\.")}${path}.* in the ${where}$`);

// ------------------------------------------------------------------------------------------------------- the page itself

test("the map draws under the page service's own policy, with no violation and no request to another origin", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, FULL);
  record("the real policy", run);
  test.info().annotations.push({ type: "run", description: show(run) });
  expect(run.version, "the page runs the pinned MapLibre").toBe("6.19.0");
  expect(failures(run)).toEqual([]);

  // The page's own worker ran, from the page's own origin: the path `worker-src 'self'` allows, with no `blob:`.
  expect(run.workers.length).toBeGreaterThan(0);
  for (const w of run.workers) expect(originOf(w), `worker at ${w}`).toBe(server.origin);
  // Every path this style gives the map was taken, so "no violation" covers each: the worker file, the style, the archive's tiles (by
  // range), the raster tile, the sprite's two files and a glyph range. A path never taken would pass by never being tried.
  const paths = run.served.map((s) => s.path);
  for (const pattern of [
    /^\/assets\/pages\/maplibre-gl-worker-[A-Z0-9]{8}\.js$/,
    /^\/fixture\/style\.json\?page=/,
    /^\/fixture\/raster\/\d+\/\d+\/\d+\.png$/,
    /^\/fixture\/sprite\.json$/,
    /^\/fixture\/sprite\.png$/,
    /^\/fixture\/glyphs\/Synthetic%20Sans\/0-255\.pbf$/,
  ]) {
    expect(paths.some((p) => pattern.test(p)), `nothing asked for ${pattern}`).toBe(true);
  }
  expect(run.tileReads).toBeGreaterThan(0);
});

// ------------------------------------------------------------------------------------- the planted faults (rule 15)
// Each runs through the same `failures()` as the page above and must be named by it.

test("planted: the archive answered whole, ignoring Range (as a forwarder without Range answers it): load and idle, no tile drawn", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, { ...FULL, archive: "whole" });
  record("archive whole", run);
  const found = failures(run);
  // The readiness check is not only `load` and `idle`: the map reaches both and draws nothing from the archive.
  expect(run.loaded && run.idle, "the map should still reach load and idle").toBe(true);
  // (Counted from 206 answers only, so "no tile block was read" is true of a 200 by construction; the picture carries the case.)
  expect(found).toContain("no tile block was read from the archive");
  expect(found).toContainEqual(expect.stringMatching(/^no water drawn from the archive's tiles/));
  expect(found).toContainEqual(expect.stringMatching(/^no land cover drawn from the archive's tiles/));
  expect(found).toContainEqual(expect.stringMatching(/HTTP Byte Serving/));
  expect(run.violations).toEqual([]);
});

test("planted: the page sends a policy of its own (img-src *), not the builder's", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, { ...FULL, plant: setDirective("img-src", "*") });
  record("img-src *", run);
  // Nothing in the map notices a weaker policy, so only the comparison with the builder's own output can.
  const found = failures(run);
  expect(found[0]).toMatch(/^the policy sent is not the builder's own: .*img-src \*/);
  // The worker's response carries the plant too, and is named for it; nothing else is.
  expect(found.slice(1).every((f) => /^the worker's policy is not the builder's own: .*img-src \*/.test(f))).toBe(true);
});

test("planted: worker-src taken out of the policy: the worker still runs, under script-src 'self' (the fallback)", async ({ page, browserName }) => {
  // The brief's plant (i). It cannot turn the run red: CSP Level 3 falls back from `worker-src` to `script-src`, and the
  // builder's `script-src 'self'` allows a same-origin worker. Kept as a case so the fallback is on record, and so that a
  // browser that stopped falling back would show here.
  const run = await openMap(page, browserName, { ...FULL, plant: dropDirective("worker-src") });
  record("worker-src dropped", run);
  const found = failures(run);
  expect(found[0]).toMatch(/^the policy sent is not the builder's own: /);
  expect(found.slice(1).every((f) => f.startsWith("the worker's policy is not the builder's own: "))).toBe(true);
  expect(run.policy.received).not.toMatch(/worker-src/);
});

test("planted: worker-src 'none': the worker is refused, by name, and the map never loads", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, { ...FULL, plant: setDirective("worker-src", "'none'") });
  record("worker-src 'none'", run);
  const found = failures(run);
  expect(found).toContainEqual(expect.stringMatching(/^policy violation: worker-src refused http:\/\/127\.0\.0\.1:\d+\/assets\/pages\/maplibre-gl-worker-[A-Z0-9]{8}\.js in the document$/));
  expect(found).toContain("the map never reached load");
});

test("planted: the worker named on another origin (setWorkerUrl as maplibreWorker.ts calls it): a blob: worker, refused by worker-src 'self'", async ({ page, browserName }) => {
  // MapLibre wraps a cross-origin module worker in a `blob:` URL (`import "<url>"`), which `worker-src 'self'` refuses: the
  // same-origin worker is what keeps the policy free of `blob:`.
  const run = await openMap(page, browserName, { ...FULL, worker: "elsewhere" });
  record("worker elsewhere", run);
  const found = failures(run);
  expect(found).toContainEqual(expect.stringMatching(/^policy violation: worker-src refused blob(:.*)? in the document$/));
  expect(found).toContain("the map never reached load");
  expect(run.reachedElsewhere, "the refused worker's script must never have been fetched").toEqual([]);
});

for (const [caseName, style, path, where] of [
  ["a vector tile", "tile-elsewhere", "/tiles/", "worker"],
  ["a glyph range", "glyphs-elsewhere", "/fixture/glyphs/", "document"],
  ["the sprite", "sprite-elsewhere", "/fixture/sprite", "document"],
  ["a raster tile", "raster-elsewhere", "/fixture/raster/", "document"],
] as const) {
  test(`planted: a style that asks for ${caseName} from another origin: refused by connect-src, named, and never sent`, async ({ page, browserName }) => {
    const run = await openMap(page, browserName, { ...FULL, style });
    record(`${style}`, run);
    expect(failures(run)).toContainEqual(expect.stringMatching(refusedElsewhere("connect-src", path, where)));
    expect(run.reachedElsewhere, "a refused request reached the other origin").toEqual([]);
  });
}

test("planted: connect-src widened to the other origin on every response, and a style that asks it for a tile: no violation, and (b) names the request that left", async ({ page, browserName }) => {
  // The case the standing test exists for: a policy that says yes to an outside request. (a) is silent, so only (b) can see
  // it. The widening is on every response, the worker's included: a worker is governed by its own script's policy.
  const run = await openMap(page, browserName, {
    ...FULL,
    style: "tile-elsewhere",
    plant: (policy, origins) => setDirective("connect-src", `'self' ${origins.elsewhere}`)(policy, origins),
  });
  record("connect-src widened, tile elsewhere", run);
  expect(run.violations, "the widened policy refuses nothing").toEqual([]);
  expect(run.reachedElsewhere.length, "the other origin's own server saw the tile requests").toBeGreaterThan(0);
  expect(failures(run)).toContainEqual(expect.stringMatching(elsewherePath("/tiles/")));
  // And the browser's own witness saw them, apart from the other origin's server: a vector tile is fetched in the worker.
  expect(run.outside.some((u) => u.startsWith(`${server.elsewhere}/tiles/`)), "the browser's request record missed the worker's tile requests").toBe(true);
});

test("planted: connect-src widened to a third origin no server answers, and a style that asks it for a tile: only the browser's witness can name it", async ({ page, browserName }) => {
  // A real leak (a public tile host) reaches no server of this test's, so (b)'s browser half must see it alone. The spec's
  // route aborts the request, so nothing leaves the machine.
  const run = await openMap(page, browserName, {
    ...FULL,
    style: "tile-third",
    plant: (policy, origins) => setDirective("connect-src", `'self' ${THIRD_ORIGIN}`)(policy, origins),
  });
  record("connect-src widened, tile at a third origin", run);
  expect(run.violations, "the widened policy refuses nothing").toEqual([]);
  expect(run.reachedElsewhere).toEqual([]);
  expect(failures(run)).toContainEqual(expect.stringMatching(new RegExp(`^request to another origin: ${THIRD_ORIGIN.replace(/[.]/g, "\\.")}/tiles/`)));
});

test("planted: connect-src widened on the page's own response alone: the worker still refuses the outside tile, under its own policy", async ({ page, browserName }) => {
  // Finding 2, kept as a case: what governs a worker's fetch is the policy on the worker script's response.
  const run = await openMap(page, browserName, {
    ...FULL,
    style: "tile-elsewhere",
    plantScope: "page",
    plant: (policy, origins) => setDirective("connect-src", `'self' ${origins.elsewhere}`)(policy, origins),
  });
  record("connect-src widened on the page alone", run);
  expect(run.policy.received).toContain(`connect-src 'self' ${server.elsewhere}`);
  expect(run.workerPolicies.length).toBeGreaterThan(0);
  for (const w of run.workerPolicies) expect(w.sent, "the worker's own policy").toBe(w.builder);
  expect(failures(run)).toContainEqual(expect.stringMatching(refusedElsewhere("connect-src", "/tiles/", "worker")));
  expect(run.reachedElsewhere).toEqual([]);
});

test("planted: a browser without createImageBitmap: the image fallback asks for img-src blob:, refused (the only path that needs it)", async ({ page, browserName }) => {
  // `maplibre-gl` 6.19's `arrayBufferToCanvasImageSource` decodes with `createImageBitmap` where it exists, and only otherwise
  // makes an `<img>` from `URL.createObjectURL(blob)` (`arrayBufferToImage`). Both browsers have `createImageBitmap`, so the
  // page above needs no `blob:`; this takes it away to show the branch that would.
  await page.addInitScript(() => {
    delete (globalThis as unknown as { createImageBitmap?: unknown }).createImageBitmap;
  });
  const run = await openMap(page, browserName, FULL);
  record("no createImageBitmap", run);
  expect(failures(run)).toContainEqual(expect.stringMatching(/^policy violation: img-src refused blob(:.*)? in the document$/));
  expect(directivesRefused(run)).toEqual(["img-src"]);
});

test("planted: a page that adds a <style> element while it loads: refused, and named by both witnesses", async ({ page, browserName }) => {
  await page.addInitScript(() => {
    interface Element {
      textContent: string;
      appendChild(child: Element): void;
    }
    const doc = (globalThis as unknown as { document: { head: Element; createElement(tag: string): Element; addEventListener(type: string, listener: () => void): void } }).document;
    doc.addEventListener("DOMContentLoaded", () => {
      const style = doc.createElement("style");
      style.textContent = "#map { outline: 0 }";
      doc.head.appendChild(style);
    });
  });
  const run = await openMap(page, browserName, FULL);
  record("page adds a <style>", run);
  // The violation event and the console line, in both browsers.
  expect(failures(run)).toContain("policy violation: style-src-elem refused inline in the document");
  expect(failures(run)).toContainEqual(expect.stringMatching(/^refused, on the console: \[load, document\] .*style-src/));
});

for (const [unheaded, caseName, named] of [
  ["page", "the page's own route", "the page was served with no policy"],
  ["worker", "the worker's asset route", "the worker's script was served with no policy"],
] as const) {
  test(`planted: ${caseName} mounted ahead of the security headers: the map draws with no policy there, and that is named`, async ({ page, browserName }) => {
    // The map notices nothing, and a policy sent that equals the builder's own is also true of none and none.
    const run = await openMap(page, browserName, { ...FULL, unheaded });
    record(`${unheaded} unheaded`, run);
    const missing = unheaded === "page" ? [run.policy] : run.workerPolicies;
    expect(missing.length).toBeGreaterThan(0);
    for (const m of missing) expect(m, "the plant reached the browser").toMatchObject({ builder: "", sent: "" });
    expect([...new Set(failures(run))]).toEqual([named]);
  });
}

test("planted: a request refused while the picture is being read: its violation event still counts", async ({ page, browserName }) => {
  // The picture can take seconds to read, and a map goes on asking for things: (a) is every event, not those before it.
  const late = `${server.elsewhere}/late`;
  const run = await openMap(page, browserName, FULL, () =>
    page.evaluate(async (url) => {
      await fetch(url).catch(() => undefined);
    }, late),
  );
  record("refused while drawing", run);
  expect(failures(run)).toContain(`policy violation: connect-src refused ${late} in the document`);
  expect(run.reachedElsewhere).toEqual([]);
});

// --------------------------------------------------------------------------------------------- the directive table
// Each of the builder's directives set to 'none' in turn: which ones the map needs. A directive the map needs is refused by
// name; one it does not need changes nothing. A change here is not the policy failing: it is the table changing (a MapLibre
// update taking a new path), and the report's table must change with it.

const NEEDED: Record<string, boolean> = {
  "default-src": false,
  "script-src": true,
  "style-src": true,
  "img-src": false,
  "worker-src": true,
  "connect-src": true,
  "frame-src": false,
  "frame-ancestors": false,
  "object-src": false,
  "base-uri": false,
  "form-action": false,
};

test("the directive table lists every directive the builder sends", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, FULL);
  expect(directives(run.policy.builder).map(nameOf).sort()).toEqual(Object.keys(NEEDED).sort());
});

for (const [directive, needed] of Object.entries(NEEDED)) {
  test(`the directive table: ${directive} 'none' ${needed ? "is refused by name" : "changes nothing"}`, async ({ page, browserName }) => {
    const run = await openMap(page, browserName, { ...FULL, plant: setDirective(directive, "'none'") });
    record(`${directive} 'none'`, run);
    // The plant reached the browser: the page's policy and the worker's both carry it.
    expect(run.policy.received.split(";")).toContain(`${directive} 'none'`);
    for (const w of run.workerPolicies) expect(w.sent.split(";")).toContain(`${directive} 'none'`);
    expect(failures(run)).toContainEqual(expect.stringMatching(/^the policy sent is not the builder's own: /));
    const others = failures(run).filter((f) => !f.startsWith("the policy sent is not the builder's own") && !f.startsWith("the worker's policy is not"));
    if (needed) {
      expect(directivesRefused(run)).toEqual([directive]);
      if (directive === "style-src") {
        // The stylesheet is refused and the map still draws every layer.
        expect(others.filter((f) => /^no |never reached/.test(f))).toEqual([]);
      }
    } else {
      expect(others, `${directive} 'none' changed the map`).toEqual([]);
    }
  });
}


test("the directive table: script-src with the nonce alone (no 'self')", async ({ page, browserName }) => {
  // What `script-src 'self'` is for, beyond the nonce the page's script tag carries: measured, not assumed.
  const run = await openMap(page, browserName, {
    ...FULL,
    plant: (policy, origins) => setDirective("script-src", /script-src[^;]*('nonce-[^']+')/.exec(policy)![1]!)(policy, origins),
  });
  record("script-src nonce only", run);
  expect(run.policy.received).not.toMatch(/script-src 'self'/);
  // The map still loads and draws every layer: the only things named are the two policies the plant changed.
  const others = failures(run).filter((f) => !f.startsWith("the policy sent is not the builder's own") && !f.startsWith("the worker's policy is not"));
  expect(others, "script-src with the nonce alone changed the map").toEqual([]);
});
