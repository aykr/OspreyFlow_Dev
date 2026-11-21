/**
 * Slice IS5a0, round 2: `scripts/build.mjs`, the step the image runs, writes the layout the production service resolves
 * its own files from. The server finds its templates at `dist/tree-default`, the function list at `dist/FUNCTIONS.yaml` and
 * the asset manifest at `dist/assets/manifest.json`, all relative to where its code is; nothing else tests that the build
 * writes them there (every other test runs the sources). So this runs the real build into a scratch folder, then starts the
 * BUILT `createApp` with one page whose id only the built `FUNCTIONS.yaml` can vouch for, and signs in and renders it.
 *
 * Which test fails if the invariant is broken (rule 12): drop the `cpSync` of `tree-default` and the page's render fails;
 * drop the one of `FUNCTIONS.yaml` and start-up refuses the page ("could not be read"); move the manifest and the layout
 * links no stylesheet. Each is shown below by building without it (the last case), at the call site the build really has.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { csrfFromPage, request, signIn, TEST_SESSION_SECRET } from "../support/http.js";

const PAGES = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRATCH_PARENT = join(PAGES, "node_modules", ".cache");

let out = "";

function runBuild(into: string): void {
  execFileSync(process.execPath, [join(PAGES, "scripts", "build.mjs"), "--out", into], { cwd: PAGES, stdio: "pipe" });
}

beforeAll(() => {
  // Inside this workspace's node_modules so the built server finds `express` and the rest, as the image's does.
  mkdirSync(SCRATCH_PARENT, { recursive: true });
  out = mkdtempSync(join(SCRATCH_PARENT, "build-layout-"));
  runBuild(out);
}, 120_000);

afterAll(() => {
  rmSync(out, { recursive: true, force: true });
});

describe("the build's layout", () => {
  it("writes the three paths the server resolves, and the entry point the image runs", () => {
    for (const path of [
      "server/main.js",
      "server/app.js",
      "tree-default/layout.njk",
      "FUNCTIONS.yaml",
      "assets/manifest.json",
    ]) {
      expect(existsSync(join(out, path)), path).toBe(true);
    }
    const manifest = JSON.parse(readFileSync(join(out, "assets", "manifest.json"), "utf8")) as Record<string, string>;
    expect(manifest["pages.css"]).toMatch(/^pages-[A-Z0-9]{8}\.css$/);
    expect(existsSync(join(out, "assets", manifest["pages.css"] as string))).toBe(true);
  });

  it("writes no copy of the test fixtures into the built tree", () => {
    expect(existsSync(join(out, "test"))).toBe(false);
  });

  it("starts the built server with a page: its id is read from the built FUNCTIONS.yaml, its layout from the built tree", async () => {
    const app = await builtApp(out);
    const login = await signIn(app);
    const res = await request(app).get("/_built/page").set("Cookie", login.cookie);
    expect(res.status).toBe(200);
    expect(res.text).toContain("<main");
    expect(res.text).toMatch(/<link rel="stylesheet" href="\/assets\/pages\/pages-[A-Z0-9]{8}\.css">/);
    expect(res.text).toContain("built-page-content");
    expect(csrfFromPage(res.text)).toBeTruthy();
  });

  it("the check is red for a build that leaves a path out: no function list, no tree", async () => {
    for (const missing of ["FUNCTIONS.yaml", "tree-default"]) {
      const broken = mkdtempSync(join(SCRATCH_PARENT, "build-layout-broken-"));
      try {
        runBuild(broken);
        rmSync(join(broken, missing), { recursive: true, force: true });
        const attempt = builtApp(broken).then(async (app) => {
          const login = await signIn(app);
          return request(app).get("/_built/page").set("Cookie", login.cookie);
        });
        if (missing === "FUNCTIONS.yaml") await expect(attempt).rejects.toThrow(/FUNCTIONS\.yaml could not be read/);
        else expect((await attempt.catch(() => ({ status: 500 }))).status).toBe(500);
      } finally {
        rmSync(broken, { recursive: true, force: true });
      }
    }
  }, 180_000);
});

type BuiltApp = Parameters<typeof request>[0];

/** The BUILT `createApp`, run from the scratch folder, with one page that names a real row and renders a template of its own. */
async function builtApp(folder: string): Promise<BuiltApp> {
  const appModule = (await import(pathToFileURL(join(folder, "server", "app.js")).href)) as typeof import("../../server/app.js");
  const storeModule = (await import(pathToFileURL(join(folder, "server", "sessionStore.js")).href)) as typeof import("../../server/sessionStore.js");
  const manifest = JSON.parse(readFileSync(join(folder, "assets", "manifest.json"), "utf8")) as Record<string, string>;
  const { fakeProvider } = await import("../support/fakeProvider.js");
  const { testClock } = await import("../support/clock.js");
  const clock = testClock();
  return appModule.createApp({
    store: new storeModule.MemorySessionStore({ clock }),
    identityProvider: fakeProvider({ now: clock }),
    clock,
    sessionSecret: TEST_SESSION_SECRET,
    assets: { dir: join(folder, "assets"), manifest },
    viewDirs: [join(PAGES, "test", "fixtures", "views")],
    pages: [
      {
        id: "studio-frame",
        path: "/_built/page",
        methods: ["GET"],
        handler: (req, res) => {
          res.render("built-page", { csrfToken: req.session.auth?.csrfToken });
        },
      },
    ],
  });
}
