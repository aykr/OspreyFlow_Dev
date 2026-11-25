/**
 * Slice IS5a0, round 2: `apps/pages/scripts/build.mjs`, the step the image runs, writes the layout the production service resolves
 * its own files from. The server finds its templates at `dist/tree-default`, the function list at `dist/FUNCTIONS.yaml` and
 * the asset manifest at `dist/assets/manifest.json`, all relative to where its code is; nothing else tests that the build
 * writes them there (every other test runs the sources). So this runs the real build into a scratch folder, then starts the
 * BUILT `createApp` with one page whose id only the built `FUNCTIONS.yaml` can vouch for, and signs in and renders it.
 *
 * Slice GR2a, round 2: the same for the GOV.UK tree's two build steps (the `cpSync` of `tree-govuk`, and the esbuild bundle of
 * `server/views/helpWords.ts` with the shared package's source: the image's run-time stage holds no workspace package). The built
 * service is started in a child process from a folder where `@ospreyflow/glass-shared` cannot be resolved, with
 * `OSPREY_PAGES_TREE=govuk` and the real `PAGES`, and asked for `/help`, `/` and an unknown path. Each step is shown red by running
 * the real `build.mjs` with that step's text taken out (or esbuild told to leave the package external): the build's own shape.
 *
 * Which test fails if the invariant is broken (rule 12): drop the `cpSync` of `tree-default` and the page's render fails;
 * drop the one of `FUNCTIONS.yaml` and start-up refuses the page ("could not be read"); move the manifest and the layout
 * links no stylesheet. Each is shown below by building without it (the last case), at the call site the build really has.
 */
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { csrfFromPage, request, signIn, TEST_SESSION_SECRET } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

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
        else await expect(attempt).rejects.toThrow(/anti-forgery|template not found|layout/i); // the home page cannot render either
      } finally {
        rmSync(broken, { recursive: true, force: true });
      }
    }
  }, 180_000);
});

describe("the build's GOV.UK tree steps (slice GR2a)", () => {
  it("writes the GOV.UK tree's templates, and a Help page's words that import no workspace package", () => {
    for (const file of ["layout.njk", "help.njk", "home.njk", "error.njk", "routes.yaml"]) {
      expect(existsSync(join(out, "tree-govuk", file)), file).toBe(true);
    }
    const words = readFileSync(join(out, "server", "views", "helpWords.js"), "utf8");
    expect(bareImports(words)).toEqual([]);
    // Slice GR4a: the trends page's words are bundled the same way.
    expect(bareImports(readFileSync(join(out, "server", "views", "packTrendsWords.js"), "utf8"))).toEqual([]);
    // The control for the check itself: the compiler's own output of the same file does import the package.
    expect(bareImports('import { HELP_TITLE } from "@ospreyflow/glass-shared";')).toEqual(["@ospreyflow/glass-shared"]);
  });

  it("the built service, started for the govuk tree from where the workspace package cannot be found, serves /help, / and its error page", () => {
    const run = runIsolated(build("none"));
    expect(problemsWith(run)).toEqual([]);
    expect(run.report?.help.text).toContain("<h1>Help</h1>");
    expect(run.report?.help.text).toContain('data-tree="govuk"');
  }, 120_000);

  it.each([
    ["the copy of tree-govuk", "tree", /\/help answered 500.*\/ answered 500.*unknown path answered 500/],
    ["the bundling of the Help words", "bundle", /@ospreyflow\/glass-shared/],
    ["the bundling, with esbuild leaving the shared package external", "external", /@ospreyflow\/glass-shared/],
  ] as const)("is red for a build without %s", (_name, fault, words) => {
    const built = build(fault);
    if (fault === "tree") expect(existsSync(join(built.dist, "tree-govuk", "layout.njk"))).toBe(false);
    else {
      expect(bareImports(readFileSync(join(built.dist, "server", "views", "helpWords.js"), "utf8"))).toEqual(["@ospreyflow/glass-shared"]);
      expect(bareImports(readFileSync(join(built.dist, "server", "views", "packTrendsWords.js"), "utf8"))).toEqual(["@ospreyflow/glass-shared"]);
    }
    const problems = problemsWith(runIsolated(built));
    expect(problems.length, problems.join("; ")).toBeGreaterThan(0);
    expect(problems.join("; ")).toMatch(words);
  }, 120_000);
});

// ---------------------------------------------------------------------------------- the GOV.UK tree's build, run on its own

/** The package specifiers a built file imports that are not a path or a built-in: what a run-time stage with no workspace would lack. */
function bareImports(code: string): string[] {
  return [...code.matchAll(/(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["']([^"'./][^"']*)["']/g)]
    .map((match) => match[1] as string)
    .filter((specifier) => !specifier.startsWith("node:"));
}

/**
 * The real `build.mjs` into a folder of its own under the machine's temporary folder (so no `node_modules` above it holds the
 * workspace), with one step taken out of a copy of the script. `tree` leaves out the `cpSync` of `tree-govuk`; `bundle` leaves out
 * the esbuild step (so `tsc`'s own output of `helpWords.ts`, which imports the package, stays); `external` tells esbuild to leave the
 * package external. The copy sits beside the script (it imports `./assets.mjs` and finds the package from its own place) and is
 * removed at once. A step whose text has moved is a failure here, not a silent no-op.
 */
function build(fault: "none" | "tree" | "bundle" | "external"): { dist: string; home: string } {
  const home = mkdtempSync(join(tmpdir(), "pages-govuk-build-"));
  const dist = join(home, "dist");
  const real = join(PAGES, "scripts", "build.mjs");
  const text = readFileSync(real, "utf8");
  const edits = {
    none: (t: string) => t,
    tree: (t: string) => t.replace(/^cpSync\(join\(root, "tree-govuk"\).*$/m, ""),
    bundle: (t: string) => t.replace(/^await build\(\{[\s\S]*?^\}\);$/m, ""),
    external: (t: string) => t.replace("  bundle: true,\n", '  bundle: true,\n  external: ["@ospreyflow/glass-shared"],\n'),
  };
  const changed = edits[fault](text);
  if (fault !== "none" && changed === text) throw new Error(`build.mjs no longer has the text this test takes out for "${fault}": update the test`);
  const copy = join(PAGES, "scripts", `.build-without-${fault}-${process.pid}.mjs`);
  try {
    writeFileSync(copy, changed);
    execFileSync(process.execPath, [copy, "--out", dist], { cwd: PAGES, stdio: "pipe" });
  } finally {
    rmSync(copy, { force: true });
  }
  return { dist, home };
}

interface Report {
  help: { status: number; text: string };
  home: { status: number; text: string };
  missing: { status: number; text: string };
}

/**
 * Starts the built `start.js` main (the real route table, `OSPREY_PAGES_TREE=govuk`, an in-memory store and a provider that signs in
 * anyone) in a child process, from the folder the build was written to, whose `node_modules` holds every installed package but
 * the workspace's own (`@ospreyflow/*`): what the image's run-time stage holds. The child signs in and reads the three pages.
 */
function runIsolated(built: { dist: string; home: string }): { status: number | null; stderr: string; report: Report | undefined } {
  try {
    const modules = join(built.home, "node_modules");
    mkdirSync(modules);
    for (const from of [join(PAGES, "..", "..", "node_modules"), join(PAGES, "node_modules")]) {
      if (!existsSync(from)) continue;
      for (const name of readdirSync(from)) {
        if (name.startsWith(".") || name === "@ospreyflow" || existsSync(join(modules, name))) continue;
        symlinkSync(realpathSync(join(from, name)), join(modules, name));
      }
    }
    const runner = join(built.home, "run.mjs");
    writeFileSync(
      runner,
      `import { readFileSync } from "node:fs";
import { main } from "./dist/server/start.js";
import { MemorySessionStore } from "./dist/server/sessionStore.js";
const dir = new URL("./dist/assets", import.meta.url).pathname;
const manifest = JSON.parse(readFileSync(dir + "/manifest.json", "utf8"));
const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
const running = await main(
  { OSPREY_PAGES_PORT: "0", OSPREY_PAGES_SESSION_SECRET: process.env.RUN_SECRET, OSPREY_PAGES_TREE: "govuk" },
  io,
  {
    store: new MemorySessionStore(),
    host: "127.0.0.1",
    assets: { dir, manifest },
    identityProvider: { async signIn() { return { subject: "sub-build", displayName: "Alex Example", accessToken: "x", refreshToken: "x", idpSessionExpiresAt: Date.now() + 3600000 }; } },
  },
);
try {
  const base = "http://127.0.0.1:" + running.port;
  const proxy = { "x-forwarded-proto": "https" };
  const start = await fetch(base + "/session/sign-in", { headers: proxy, redirect: "manual" });
  const cookie = start.headers.getSetCookie()[0].split(";")[0];
  const read = async (path) => { const r = await fetch(base + path, { headers: { ...proxy, cookie }, redirect: "manual" }); return { status: r.status, text: await r.text() }; };
  console.log(JSON.stringify({ help: await read("/help"), home: await read("/"), missing: await read("/no-such-page") }));
} finally {
  await running.stop();
}
`,
    );
    const child = spawnSync(process.execPath, [runner], {
      cwd: built.home,
      encoding: "utf8",
      env: { PATH: process.env["PATH"] ?? "", RUN_SECRET: generateSecret(48) },
      timeout: 60_000,
    });
    let report: Report | undefined;
    try {
      report = JSON.parse(child.stdout) as Report;
    } catch {
      report = undefined;
    }
    return { status: child.status, stderr: child.stderr, report };
  } finally {
    rmSync(built.home, { recursive: true, force: true });
  }
}

/** What is wrong with a run, in words: the same function says nothing of a good build and something of each broken one. */
function problemsWith(run: { status: number | null; stderr: string; report: Report | undefined }): string[] {
  if (!run.report) return [`the built service did not start or answer (exit ${String(run.status)}): ${run.stderr.slice(0, 400)}`];
  const problems: string[] = [];
  const { help, home, missing } = run.report;
  if (help.status !== 200 || !help.text.includes("<h1>Help</h1>")) problems.push(`/help answered ${help.status} with no Help page`);
  if (home.status !== 200 || !home.text.includes('data-tree="govuk"')) problems.push(`/ answered ${home.status} with no GOV.UK page`);
  if (missing.status !== 404 || !missing.text.includes('data-tree="govuk"')) problems.push(`an unknown path answered ${missing.status} with no GOV.UK error page`);
  return problems;
}


/** The BUILT `createApp`, run from the scratch folder, with one page that names a real row and renders a template of its own. */
async function builtApp(folder: string): Promise<Express> {
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
