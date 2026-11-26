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
// `failures()` turns a record into the list of what is wrong. The page under the real policy must have none. Every planted fault
// below (rule 15: each the shape the page really sends or receives at its own call site) runs through the same `failures()`
// and must be named by it: a check is not believed until it has been shown red.
//
//   npm run test:csp --workspace apps/pages        (its CI job is `ci-wiring.patch` beside this file, for the owner to apply)
import { inflateSync } from "node:zlib";

import { expect, test } from "@playwright/test";
import type { Page, Worker } from "@playwright/test";

import { COLOURS, RASTER_OPACITY, startMapServer } from "./mapServer.js";
import type { MapServer, PageRequest, PolicyPlant } from "./mapServer.js";

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
  workers: string[];
}

const READY_MS = 12_000;

let server: MapServer;
test.beforeAll(async () => {
  server = await startMapServer();
});
test.afterAll(async () => {
  await server?.close();
});

// ------------------------------------------------------------------------------------------------------------ recording

/** Installed in the document before any of its own script runs, and in each worker as soon as it is seen. */
function recordViolations(where: "document" | "worker"): void {
  const scope = globalThis as unknown as { __CSP__?: unknown[]; addEventListener: typeof addEventListener };
  if (scope.__CSP__) return;
  const seen: unknown[] = [];
  scope.__CSP__ = seen;
  scope.addEventListener("securitypolicyviolation", (event) => {
    const e = event as SecurityPolicyViolationEvent;
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

async function openMap(page: Page, browser: string, request: PageRequest): Promise<Run> {
  const servedBefore = server.served.length;
  const elsewhereBefore = server.reachedElsewhere.length;
  const policiesBefore = server.policies.length;
  const outside: string[] = [];
  const consoleRefusals: string[] = [];
  const pageErrors: string[] = [];
  const workers: Worker[] = [];

  await page.addInitScript(recordViolations, "document");
  page.on("worker", (worker) => {
    workers.push(worker);
    void worker.evaluate(recordViolations, "worker").catch(() => undefined);
  });
  page.on("request", (req) => {
    if (isNetwork(req.url()) && originOf(req.url()) !== server.origin) outside.push(req.url());
  });
  page.on("console", (message) => {
    if (/content security policy|refused to/i.test(message.text())) consoleRefusals.push(message.text());
  });
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
    .waitForFunction(() => window.__MAP_STATE__?.idle === true, undefined, { timeout: READY_MS })
    .catch(() => undefined);
  // Late reports: a worker's refusal or the last tile's error event.
  await page.waitForTimeout(750);

  const state = await page.evaluate(() => ({
    version: window.__MAP_STATE__?.version ?? "",
    loaded: window.__MAP_STATE__?.loaded ?? false,
    idle: window.__MAP_STATE__?.idle ?? false,
    errors: window.__MAP_STATE__?.errors ?? [],
    csp: ((globalThis as unknown as { __CSP__?: Violation[] }).__CSP__ ?? []) as Violation[],
  }));
  const violations: Violation[] = [...state.csp];
  for (const worker of workers) {
    const inWorker = await worker
      .evaluate(() => ((globalThis as unknown as { __CSP__?: unknown[] }).__CSP__ ?? []) as unknown[])
      .catch(() => [] as unknown[]);
    violations.push(...(inWorker as Violation[]));
  }
  const drawn = state.idle ? await coloursDrawn(page) : { water: 0, landcover: 0, raster: 0 };
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
    workers: workers.map((w) => w.url()),
  };
}

// ---------------------------------------------------------------------------------------------------------- the picture

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}

/** An 8-bit RGB or RGBA PNG, as Playwright's screenshots are, decoded to RGBA (no interlacing; filters 0 to 4). */
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
 * tile is the background alone. Read from a screenshot: a WebGL canvas's drawing buffer is cleared once presented. */
async function coloursDrawn(page: Page): Promise<{ water: number; landcover: number; raster: number }> {
  const shot = decodePng(await page.locator("canvas.maplibregl-canvas").screenshot());
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
  for (const url of new Set([...run.outside, ...run.reachedElsewhere])) out.push(`request to another origin: ${url}`);
  if (run.policy.received !== run.policy.builder) out.push(`the policy sent is not the builder's own: ${run.policy.received}`);
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
  return JSON.stringify({ ...run, policy: { builder: run.policy.builder.replace(/nonce-[^']+/, "nonce-N") } }, null, 1);
}

// ----------------------------------------------------------------------------------------------------------- the cases

test("the map draws under the page service's own policy, with no violation and no request to another origin", async ({ page, browserName }) => {
  const run = await openMap(page, browserName, FULL);
  test.info().annotations.push({ type: "run", description: show(run) });
  console.log(`[${browserName}] full: ${show(run)}`);
  expect(run.version).toBe("6.19.0");
  expect(failures(run)).toEqual([]);
  // The page's own worker ran, from the page's own origin: the path `worker-src 'self'` allows.
  expect(run.workers.length).toBeGreaterThan(0);
  for (const w of run.workers) expect(originOf(w), `worker at ${w}`).toBe(server.origin);
});
