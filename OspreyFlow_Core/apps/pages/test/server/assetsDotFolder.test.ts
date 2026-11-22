/**
 * Slice IS5a0, round 4: the asset route under a folder whose name starts with a dot.
 *
 * The route refuses a dot-segment inside the asset folder (`plainSegments`). Round 3 handed `res.sendFile` the absolute path, and
 * `send` then applied its own dotfile rule to every segment of that path, so a checkout or deployment under `~/.ospreyflow/...`
 * or `node_modules/.cache/...` answered 403 for every asset, which the route turned into a 404 already marked `immutable` for a
 * year. Every earlier test served from `tmpdir()`, which has no dot-segment, so none could see it (rule 15: the planted shape is
 * the folder the build really writes into, `apps/pages/node_modules/.cache/...` being one `buildLayout.test.ts` uses).
 *
 * Which test fails if the invariant is broken (rule 12): the first two fail against a route that hands `send` the absolute path;
 * the third fails against a route that sets `immutable` before it knows the file can be sent.
 */
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { build } from "../support/build.js";
import { request } from "../support/http.js";

const MANIFEST = { "pages.css": "pages-ABCD1234.css" };

let scratch = "";
let dir = "";

beforeAll(() => {
  scratch = mkdtempSync(join(tmpdir(), "pages-dotfolder-"));
  dir = join(scratch, ".ospreyflow", "node_modules", ".cache", "assets");
  mkdirSync(join(dir, "sub"), { recursive: true });
  writeFileSync(join(dir, "pages-ABCD1234.css"), "body{margin:0}");
  writeFileSync(join(dir, "sub", "inner-ABCD1234.css"), "a{b:c}");
  writeFileSync(join(dir, "locked-ABCD1234.css"), "a{b:c}");
});

afterAll(() => {
  rmSync(scratch, { recursive: true, force: true });
});

describe("the asset route under a folder with a dot in its path", () => {
  it("serves a file, immutable, though the folder sits under dot-named folders", async () => {
    const { app } = build({ assets: { dir, manifest: MANIFEST } });
    const res = await request(app).get("/assets/pages/pages-ABCD1234.css");
    expect(res.status).toBe(200);
    expect(res.text).toBe("body{margin:0}");
    expect(res.headers["cache-control"]).toBe("public, max-age=31536000, immutable");
    expect(res.headers["content-type"]).toMatch(/^text\/css/);
  });

  it("serves a file in a subfolder, and still refuses a dot-segment inside the folder", async () => {
    const { app } = build({ assets: { dir, manifest: MANIFEST } });
    expect((await request(app).get("/assets/pages/sub/inner-ABCD1234.css")).status).toBe(200);
    const dotted = await request(app).get("/assets/pages/.hidden-ABCD1234.css");
    expect(dotted.status).toBe(404);
    expect(dotted.headers["cache-control"]).not.toMatch(/immutable/);
  });

  it.skipIf(process.getuid?.() === 0)("a file the route cannot read is a 404 that is not cached for a year", async () => {
    chmodSync(join(dir, "locked-ABCD1234.css"), 0o000);
    try {
      const { app } = build({ assets: { dir, manifest: MANIFEST } });
      const res = await request(app).get("/assets/pages/locked-ABCD1234.css");
      expect(res.status).toBe(404);
      expect(res.headers["cache-control"]).not.toMatch(/immutable/);
    } finally {
      chmodSync(join(dir, "locked-ABCD1234.css"), 0o644);
    }
  });
});
