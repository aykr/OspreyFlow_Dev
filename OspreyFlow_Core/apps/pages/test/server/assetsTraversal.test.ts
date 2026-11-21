/**
 * Slice IS5a0, round 3: the asset route's containment, probed with an outside file of the shape the route would serve.
 *
 * Round 2's probes in `foundation.test.ts` aim at `secret.txt` and `server/app.ts`: a name with no hash and a type nobody
 * serves, which the route's own type and hash filter refuses before containment is ever asked. Those probes pass whether or
 * not the `..` refusal (`plainSegments`) and the folder-prefix check hold (rule 15: they would be green with both deleted).
 * Here the planted files are named `outside-ABCD1234.css`, a hashed stylesheet, beside the served folder and in a sibling
 * folder whose name starts with the served folder's name, so the only thing between the probe and the file is containment.
 *
 * Which test fails if the invariant is broken (rule 12): `the probe is red against a route that filters by type and hash
 * and nothing else` is the shape a first attempt takes once the filter is in; it leaks, so the probe can fail at this shape.
 * Then the real route is probed with the same paths and must not. Deleting both the dot-segment refusal and the prefix check
 * from `server/assets.ts` makes the real-route case fail (shown by hand in the round's report); the realpath layer, a link out
 * of the folder, is `assets.test.ts`'s.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import express from "express";
import type { Express } from "express";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { isHashed } from "../../server/assets.js";
import { build } from "../support/build.js";
import { request } from "../support/http.js";

const SECRET = `outside-served-shape-${randomBytes(12).toString("hex")}`;
const MANIFEST = { "pages.css": "pages-ABCD1234.css" };

let root = "";
let dir = "";

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), "pages-traversal-"));
  dir = join(root, "assets");
  mkdirSync(join(dir, "sub"), { recursive: true });
  mkdirSync(join(root, "assets-sibling"), { recursive: true });
  writeFileSync(join(dir, "pages-ABCD1234.css"), "body{margin:0}");
  writeFileSync(join(dir, "sub", "inner-ABCD1234.css"), "a{b:c}");
  // The shape the route serves, one level up and in a folder whose name begins with the served folder's.
  writeFileSync(join(root, "outside-ABCD1234.css"), SECRET);
  writeFileSync(join(root, "assets-sibling", "sibling-ABCD1234.css"), SECRET);
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

/** Every spelling of "one folder up" a request can carry, aimed at a file the type and hash filter would let through. */
const PROBES = [
  "..%2foutside-ABCD1234.css",
  "..%2Foutside-ABCD1234.css",
  "%2e%2e%2foutside-ABCD1234.css",
  "%2E%2E%2Foutside-ABCD1234.css",
  "%2e%2e/outside-ABCD1234.css",
  "sub/..%2f..%2foutside-ABCD1234.css",
  "sub%2f..%2f..%2foutside-ABCD1234.css",
  "..%2fassets-sibling%2fsibling-ABCD1234.css",
  "%2e%2e%2fassets-sibling%2fsibling-ABCD1234.css",
  "..%5coutside-ABCD1234.css",
  "%252e%252e%252foutside-ABCD1234.css",
  "..%2foutside-ABCD1234.css%00.css",
];

/** The probes that brought an outside file's content back, so a leaking route is named, not only counted. */
async function leaks(app: Express): Promise<string[]> {
  const found: string[] = [];
  for (const probe of PROBES) {
    const res = await request(app).get(`/assets/pages/${probe}`);
    if (res.status === 200 && (res.text ?? "").includes(SECRET)) found.push(probe);
  }
  return found;
}

/** A route with the type and hash filter and no containment: decode, join to the folder, send. */
function filterOnlyRoute(): Express {
  const app = express();
  app.get("/assets/pages/*splat", (req, res) => {
    const rest = decodeURIComponent((req.params as unknown as { splat: string[] }).splat.join("/"));
    if (!/\.css$/.test(rest) || !isHashed(rest)) {
      res.status(404).send("Not found");
      return;
    }
    res.sendFile(resolve(dir, rest));
  });
  return app;
}

describe("the asset route's containment, at the shape the route serves", () => {
  it("the outside files are really served-shaped: the filter alone lets them through, and the folder's own file is served", async () => {
    expect(isHashed("outside-ABCD1234.css")).toBe(true);
    expect(isHashed("assets-sibling/sibling-ABCD1234.css")).toBe(true);
    const { app } = build({ assets: { dir, manifest: MANIFEST } });
    expect((await request(app).get("/assets/pages/pages-ABCD1234.css")).status).toBe(200);
    expect((await request(app).get("/assets/pages/sub/inner-ABCD1234.css")).status).toBe(200);
  });

  it("the probe is red against a route that filters by type and hash and nothing else", async () => {
    const found = await leaks(filterOnlyRoute());
    expect(found).toContain("..%2foutside-ABCD1234.css");
    expect(found).toContain("%2e%2e%2foutside-ABCD1234.css");
    expect(found).toContain("..%2fassets-sibling%2fsibling-ABCD1234.css");
  });

  it("the real route returns none of them, and refuses each", async () => {
    const { app } = build({ assets: { dir, manifest: MANIFEST } });
    expect(await leaks(app)).toEqual([]);
    for (const probe of PROBES) {
      const res = await request(app).get(`/assets/pages/${probe}`);
      expect([400, 403, 404], probe).toContain(res.status);
      expect(res.text, probe).not.toContain(SECRET);
      expect(res.headers["cache-control"], probe).not.toMatch(/immutable/);
    }
  });
});
