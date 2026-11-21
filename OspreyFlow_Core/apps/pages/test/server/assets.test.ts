/**
 * The asset route's own edges and the service's start with and without the built assets (slice IS5a0; ADR-152 decision 7).
 * `foundation.test.ts` holds the route's behaviour for the folder as the build writes it; this holds what a folder can
 * hold that the build never writes (a link out of it), the hashed-name rule, and what a production start does with no build.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { isHashed } from "../../server/assets.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running, StartDeps } from "../../server/start.js";
import { build } from "../support/build.js";
import { captureOutput } from "../support/capture.js";
import { request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

const SECRET = `linked-from-outside-${randomBytes(12).toString("hex")}`;
let root = "";
let dir = "";

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), "pages-assets-"));
  dir = join(root, "assets");
  mkdirSync(dir, { recursive: true });
  mkdirSync(join(root, "outside"));
  writeFileSync(join(dir, "app-ABCD1234.css"), "a{b:c}");
  writeFileSync(join(root, "outside", "leak-ABCD1234.css"), SECRET);
  symlinkSync(join(root, "outside", "leak-ABCD1234.css"), join(dir, "linked-ABCD1234.css"));
  symlinkSync(join(root, "outside"), join(dir, "ABCD1234"));
  writeFileSync(join(dir, "manifest.json"), JSON.stringify({ "pages.css": "app-ABCD1234.css" }));
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("a file is named for its content, or it is not served", () => {
  it.each([
    ["pages-ABCD1234.css", true],
    ["fixture-5U2ATADW.js", true],
    ["fonts/2CTSZR2S/atkinson-hyperlegible-next-latin-400-normal.woff2", true],
    ["plain.css", false],
    ["pages-abcd1234.css", false], // lower case is not the build's alphabet
    ["pages-ABCD123.css", false], // seven characters
    ["pages-ABCD12345.css", false], // nine
    ["fonts/atkinson-latin-400-normal.woff2", false],
    ["ABCD1234", false], // a name with no extension is not a file the build wrote
  ])("%s: %s", (name, hashed) => {
    expect(isHashed(name)).toBe(hashed);
  });
});

describe("a link out of the folder", () => {
  it("is refused, to a file and to a folder, and the file's content is never sent", async () => {
    const { app } = build({ assets: { dir, manifest: { "pages.css": "app-ABCD1234.css" } } });
    expect((await request(app).get("/assets/pages/app-ABCD1234.css")).status).toBe(200); // the control
    for (const path of ["/assets/pages/linked-ABCD1234.css", "/assets/pages/ABCD1234/leak-ABCD1234.css"]) {
      const res = await request(app).get(path);
      expect(res.status, path).toBe(404);
      expect(res.text, path).not.toContain(SECRET);
    }
  });
});

const running: Running[] = [];
afterEach(async () => {
  while (running.length) await running.pop()?.stop();
});

async function start(env: NodeJS.ProcessEnv, assets: StartDeps["assets"]) {
  const captured = captureOutput();
  const exits: number[] = [];
  const errors: string[] = [];
  let result: Running | undefined;
  try {
    result = await main(
      { OSPREY_PAGES_PORT: "0", OSPREY_PAGES_SESSION_SECRET: generateSecret(), ...env },
      { log: () => undefined, error: (m) => void errors.push(m), exit: (c) => void exits.push(c) },
      { store: new MemorySessionStore(), host: "127.0.0.1", assets },
    );
  } finally {
    captured.restore();
  }
  if (result) running.push(result);
  return { result, exits, errors };
}

describe("a production start", () => {
  it("refuses, in words, when the assets were not built", async () => {
    const { result, exits, errors } = await start({ NODE_ENV: "production" }, null);
    expect(result).toBeUndefined();
    expect(exits).toEqual([1]);
    expect(errors.join("\n")).toMatch(/built assets are missing/);
    expect(errors.join("\n")).toContain("npm run build");
  });

  it("starts with them, serves the stylesheet, and links it from a page", async () => {
    const { result, exits } = await start({ NODE_ENV: "production" }, { dir, manifest: { "pages.css": "app-ABCD1234.css" } });
    expect(exits).toEqual([]);
    expect(result).toBeDefined();
    const base = `http://127.0.0.1:${result?.port}`;
    const css = await fetch(`${base}/assets/pages/app-ABCD1234.css`);
    expect(css.status).toBe(200);
    expect(css.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
    const missing = await fetch(`${base}/no/such/page`);
    expect(await missing.text()).toContain('<link rel="stylesheet" href="/assets/pages/app-ABCD1234.css">');
  });

  it("is a production rule: a start from the sources with no build goes on, and links no stylesheet", async () => {
    const { result, exits } = await start({}, null);
    expect(exits).toEqual([]);
    expect(result).toBeDefined();
    const page = await fetch(`http://127.0.0.1:${result?.port}/no/such/page`);
    expect(await page.text()).not.toContain('rel="stylesheet"');
  });
});
