/**
 * Slice IS5a0, the page foundation (ADR-152 decisions 6, 7 and 8): the first real page of the `pages` service can be built on it.
 *
 *   1. Static assets at `/assets/pages/*`: only the built folder, only content-hashed files, immutable, no session, and a
 *      path outside the folder refused.
 *   2. The Default tree's layout (`tree-default/`) and the route-module convention (`{ id, path, methods, handler }`),
 *      behind the session check and the anti-forgery check, with its three start-up refusals.
 *   3. The client-script bundle: hashed ES modules in the assets folder, resolving `packages/glass-shared`'s source, lowered
 *      to ES2018, no React, no inline script anywhere, and every page's core content in its HTML with scripts off.
 *
 * Which test fails if each invariant is broken (rule 12): the traversal case against a naive route
 * (`the traversal probe is red against a route that joins the decoded path`) shows the probe can fail, so the same probe
 * passing against the real route means something; the convention's refusals are planted at `createApp`, the call site
 * the server's start-up really makes; the fixture page is a template of this folder's own, never in the product tree.
 *
 * Nothing here is, or looks like, a secret: the one "secret" the traversal probe hunts for is a random string made at run time.
 */
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";
import type { Express } from "express";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import type { SessionStore } from "../../server/sessionStore.js";
import { build } from "../support/build.js";
import { fixturePage } from "../fixtures/pages.js";
import { csrfFromPage, request, signIn } from "../support/http.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGES = join(HERE, "..", "..");
const FIXTURES = join(PAGES, "test", "fixtures");
const FIXTURE_VIEWS = [join(FIXTURES, "views")];

// ------------------------------------------------------------------------------------------------ a synthetic assets folder

const SECRET = `outside-the-folder-${randomBytes(12).toString("hex")}`;
const IMMUTABLE = "public, max-age=31536000, immutable";
const MANIFEST = { "pages.css": "pages-ABCD1234.css", "modules/fixture.ts": "fixture-QWER5678.js" };

let root = "";
let dir = "";

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), "pages-foundation-"));
  dir = join(root, "assets");
  mkdirSync(join(dir, "fonts", "FONTHASH"), { recursive: true });
  mkdirSync(join(dir, ".git"), { recursive: true });
  mkdirSync(join(dir, "sub"), { recursive: true });
  writeFileSync(join(root, "secret.txt"), SECRET);
  writeFileSync(join(dir, "pages-ABCD1234.css"), "body{margin:0}");
  writeFileSync(join(dir, "fixture-QWER5678.js"), "export const a = 1;");
  writeFileSync(join(dir, "fonts", "FONTHASH", "face-latin-400-normal.woff2"), "wOF2-not-a-real-font");
  writeFileSync(join(dir, "plain.css"), "body{margin:1px}"); // not hashed: it must never be served as immutable
  writeFileSync(join(dir, ".hidden-ABCD1234.css"), "dot");
  writeFileSync(join(dir, ".git", "config"), "dot");
  writeFileSync(join(dir, "sub", "inner-ABCD1234.css"), "a{b:c}");
  writeFileSync(join(dir, "manifest.json"), "{}"); // the build's own record: not public
  writeFileSync(join(dir, "tool-ABCD1234.exe"), "MZ"); // a hashed name with a type nobody serves
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

function served(options: Parameters<typeof build>[0] = {}) {
  return build({ assets: { dir, manifest: MANIFEST }, viewDirs: FIXTURE_VIEWS, ...options });
}

// ----------------------------------------------------------------------------------------------------- 1. static assets

describe("static assets at /assets/pages/*", () => {
  it("serves a hashed stylesheet, script and font with the right type and an immutable year of caching", async () => {
    const { app } = served();
    const cases: [string, RegExp][] = [
      ["/assets/pages/pages-ABCD1234.css", /^text\/css/],
      ["/assets/pages/fixture-QWER5678.js", /^text\/javascript/],
      ["/assets/pages/fonts/FONTHASH/face-latin-400-normal.woff2", /^font\/woff2/],
    ];
    for (const [path, type] of cases) {
      const res = await request(app).get(path);
      expect(res.status, path).toBe(200);
      expect(res.headers["content-type"], path).toMatch(type);
      expect(res.headers["cache-control"], path).toBe(IMMUTABLE);
      expect(res.headers["x-content-type-options"], path).toBe("nosniff");
      expect(res.headers["content-security-policy"], path).toBeDefined();
    }
    expect((await request(app).get("/assets/pages/pages-ABCD1234.css")).text).toBe("body{margin:0}");
  });

  it("is served with no session: no cookie set, no call to the store", async () => {
    let calls = 0;
    const { app } = served({
      wrapStore: (inner): SessionStore =>
        new Proxy(inner, {
          get(target, key, receiver) {
            const value: unknown = Reflect.get(target, key, receiver);
            return typeof value === "function"
              ? (...args: unknown[]) => {
                  calls += 1;
                  return (value as (...a: unknown[]) => unknown).apply(target, args);
                }
              : value;
          },
        }),
    });
    const res = await request(app).get("/assets/pages/pages-ABCD1234.css");
    expect(res.status).toBe(200);
    expect(res.headers["set-cookie"]).toBeUndefined();
    expect(calls).toBe(0);
  });

  it("allows HEAD, with the same headers and no body", async () => {
    const { app } = served();
    const res = await request(app).head("/assets/pages/pages-ABCD1234.css");
    expect(res.status).toBe(200);
    expect(res.headers["cache-control"]).toBe(IMMUTABLE);
    expect(res.headers["content-type"]).toMatch(/^text\/css/);
    expect(res.text ?? "").toBe("");
  });

  it("refuses every other method, and says which are allowed", async () => {
    const { app } = served();
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const res = await request(app)[method]("/assets/pages/pages-ABCD1234.css");
      expect(res.status, method).toBe(405);
      expect(res.headers["allow"], method).toBe("GET, HEAD");
    }
  });

  it("lists no directory, redirects nowhere, and serves nothing that is not a hashed file of a known type", async () => {
    const { app } = served();
    for (const path of [
      "/assets/pages",
      "/assets/pages/",
      "/assets/pages/fonts",
      "/assets/pages/fonts/",
      "/assets/pages/sub/",
      "/assets/pages/plain.css", // unhashed: immutable caching would keep a stale copy for a year
      "/assets/pages/manifest.json",
      "/assets/pages/tool-ABCD1234.exe",
      "/assets/pages/missing-ABCD1234.css",
    ]) {
      const res = await request(app).get(path);
      expect(res.status, path).toBe(404);
      expect(res.headers["location"], path).toBeUndefined();
      expect(res.headers["cache-control"], path).not.toMatch(/immutable/);
    }
    // The positive control: a hashed file in a sub-folder is served, so the refusals above are not a blanket one.
    expect((await request(app).get("/assets/pages/sub/inner-ABCD1234.css")).status).toBe(200);
  });

  it("serves no dotfile and no dot-folder", async () => {
    const { app } = served();
    // The control: the folder is served, so a 404 below is the route's refusal and not an absent route.
    expect((await request(app).get("/assets/pages/pages-ABCD1234.css")).status).toBe(200);
    for (const path of ["/assets/pages/.hidden-ABCD1234.css", "/assets/pages/.git/config", "/assets/pages/.git/", "/assets/pages/sub/.hidden-ABCD1234.css"]) {
      const res = await request(app).get(path);
      expect(res.status, path).toBe(404);
      expect(res.text, path).not.toContain("dot");
    }
  });

  /**
   * Every spelling of "one folder up" the route could meet, as the browser or a script writes it: the slash encoded,
   * the dots encoded, mixed case in the escape, a backslash, a double encoding. Returns each probe that brought the
   * outside file's content back, so a route that leaks is named, not just counted.
   */
  async function leaks(app: Express): Promise<string[]> {
    const probes = [
      "..%2fsecret.txt",
      "..%2Fsecret.txt",
      "%2e%2e%2fsecret.txt",
      "%2e%2e/secret.txt",
      "sub/..%2f..%2fsecret.txt",
      "..%2f..%2fserver%2fapp.ts",
      "..%5csecret.txt",
      "%252e%252e%252fsecret.txt",
    ];
    const found: string[] = [];
    for (const probe of probes) {
      const res = await request(app).get(`/assets/pages/${probe}`);
      if (res.status === 200 && (res.text ?? "").includes(SECRET)) found.push(probe);
    }
    return found;
  }

  /** The shape a first attempt takes: route by prefix, decode the rest, join it to the folder, send the file. */
  function naiveRoute(): Express {
    const app = express();
    app.get("/assets/pages/*splat", (req, res) => {
      const rest = (req.params as unknown as { splat: string[] }).splat.join("/");
      res.sendFile(join(dir, decodeURIComponent(rest)));
    });
    return app;
  }

  it("the traversal probe is red against a route that joins the decoded path", async () => {
    const found = await leaks(naiveRoute());
    expect(found).toContain("..%2fsecret.txt");
    expect(found).toContain("%2e%2e%2fsecret.txt");
  });

  it("refuses a path outside the folder, plain and encoded, and never returns the outside file", async () => {
    const { app } = served();
    // The probe's own control: the real route serves the folder's file, so a 404 for every probe is not an absent route.
    expect((await request(app).get("/assets/pages/pages-ABCD1234.css")).status).toBe(200);
    expect(await leaks(app)).toEqual([]);
    for (const probe of ["..%2fsecret.txt", "%2e%2e%2fsecret.txt", "sub/..%2f..%2fsecret.txt"]) {
      const res = await request(app).get(`/assets/pages/${probe}`);
      expect([400, 403, 404], probe).toContain(res.status);
      expect(res.text, probe).not.toContain(SECRET);
    }
  });

  it("keeps the page headers: the policy has no inline allowance, and a page is still never stored", async () => {
    const { app } = served();
    const page = await request(app).get("/no/such/page");
    expect(page.headers["cache-control"]).toBe("no-store");
    const policy = page.headers["content-security-policy"] as string;
    expect(policy).toContain("script-src 'self' 'nonce-");
    expect(policy).toContain("style-src 'self' 'nonce-");
    expect(policy).not.toMatch(/unsafe-inline|unsafe-eval/);
  });
});

// ---------------------------------------------------------------------------- 2. the layout and the route-module convention

/** The inline-code check ADR-152 decision 8 asks of every template: no script with code, no style, no handler attribute. */
function inlineCode(template: string): string[] {
  const found: string[] = [];
  for (const m of template.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
    const attributes = m[1] ?? "";
    const body = (m[2] ?? "").trim();
    const data = /\btype\s*=\s*["']application\/(?:json|ld\+json)["']/i.test(attributes);
    const external = /\bsrc\s*=/i.test(attributes) && body === "";
    if (!data && !external) found.push(m[0].slice(0, 60));
  }
  for (const m of template.matchAll(/<style\b/gi)) found.push(`a <style> element at ${m.index}`);
  for (const m of template.matchAll(/<[a-z][^>]*\sstyle\s*=/gi)) found.push(`a style attribute: ${m[0].slice(0, 40)}`);
  for (const m of template.matchAll(/<[a-z][^>]*\son[a-z]+\s*=/gi)) found.push(`an event-handler attribute: ${m[0].slice(0, 40)}`);
  for (const m of template.matchAll(/href\s*=\s*["']\s*javascript:/gi)) found.push(`a javascript: link at ${m.index}`);
  return found;
}

function templatesIn(folder: string): string[] {
  if (!existsSync(folder)) return [];
  return readdirSync(folder, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".njk"))
    .map((e) => join(e.parentPath, e.name));
}

describe("the Default tree's layout", () => {
  it("lives in tree-default/, and the tree's templates are there and nowhere else", () => {
    const names = templatesIn(join(PAGES, "tree-default")).map((p) => p.slice(PAGES.length + 1));
    expect(names).toEqual(expect.arrayContaining(["tree-default/layout.njk", "tree-default/home.njk", "tree-default/error.njk"]));
    expect(templatesIn(join(PAGES, "server", "views"))).toEqual([]);
  });

  it("has the stylesheet link, lang en-GB, a skip link first, a header with the product name and a sign-out form, a main landmark and no footer", async () => {
    const { app } = served({ pages: [fixturePage()] });
    const { cookie, csrf } = await signIn(app);
    const res = await request(app).get("/_fixture/page").set("Cookie", cookie);
    expect(res.status).toBe(200);
    const html = res.text;
    expect(html).toContain('<html lang="en-GB">');
    expect(html).toContain('<link rel="stylesheet" href="/assets/pages/pages-ABCD1234.css">');
    expect(html).toMatch(/<title>Fixture page · OspreyFlow<\/title>/);
    // The skip link is the first thing in the body, and its target is the main landmark.
    const body = html.slice(html.indexOf("<body"));
    expect(body.slice(body.indexOf(">") + 1).trimStart()).toMatch(/^<a [^>]*href="#main"[^>]*>Skip to main content<\/a>/);
    expect(html).toMatch(/<main id="main"[^>]*>/);
    expect(html.match(/<main\b/g)).toHaveLength(1);
    expect(html).not.toMatch(/<footer\b/);
    // The header carries the product name and a POST sign-out form with this session's token.
    const header = /<header\b[\s\S]*?<\/header>/.exec(html)?.[0] ?? "";
    expect(header).toContain("OspreyFlow");
    expect(header).toMatch(/<form method="post" action="\/session\/sign-out">/);
    expect(csrfFromPage(header)).toBe(csrf);
    expect(html.indexOf("<header")).toBeLessThan(html.indexOf("<main"));
    // The page-data block and the script are the page's own, and the script is a file, never inline code.
    expect(html).toMatch(/<script type="application\/json" id="page-data" nonce="[^"]+">\{"page":"fixture","rows":2\}<\/script>/);
    expect(html).toContain('<script type="module" src="/assets/pages/fixture-QWER5678.js"></script>');
  });

  it("gives a signed-out page (an error) the same frame without a sign-out form", async () => {
    const { app } = served();
    const res = await request(app).get("/no/such/page");
    expect(res.status).toBe(404);
    expect(res.text).toContain('<html lang="en-GB">');
    expect(res.text).toContain('href="#main"');
    expect(res.text).toContain('<link rel="stylesheet" href="/assets/pages/pages-ABCD1234.css">');
    expect(res.text).not.toContain("/session/sign-out");
  });

  it("holds no inline script with code, no style and no handler attribute, in any template or any page it sends", async () => {
    const templates = [...templatesIn(join(PAGES, "tree-default")), ...templatesIn(FIXTURES)];
    expect(templates.length).toBeGreaterThanOrEqual(4);
    for (const path of templates) expect(inlineCode(readFileSync(path, "utf8")), path).toEqual([]);
    const { app } = served({ pages: [fixturePage()] });
    const { cookie } = await signIn(app);
    for (const [name, res] of [
      ["the home page", await request(app).get("/").set("Cookie", cookie)],
      ["the fixture page", await request(app).get("/_fixture/page").set("Cookie", cookie)],
      ["a 404", await request(app).get("/nowhere")],
    ] as const) {
      expect(res.status, name).toBeLessThan(500);
      expect(inlineCode(res.text), name).toEqual([]);
    }
  });

  it("the inline-code check is red for each shape an inline script takes", () => {
    const planted = [
      '<script nonce="{{ cspNonce }}">window.open("/x")</script>',
      "<script>\nfetch('/v1/x')\n</script>",
      '<script type="module">import "/a.js";</script>',
      '<script src="/a.js">alert(1)</script>',
      "<style>body{color:red}</style>",
      '<div style="color:red">x</div>',
      '<button onclick="go()">x</button>',
      '<a href="javascript:go()">x</a>',
    ];
    for (const html of planted) expect(inlineCode(`<main>${html}</main>`), html).not.toEqual([]);
    // And the two shapes that are not code.
    expect(inlineCode('<script type="application/json" id="page-data" nonce="{{ cspNonce }}">{"page":"x"}</script>')).toEqual([]);
    expect(inlineCode('<script type="module" src="{{ asset(\'modules/x.ts\') }}"></script>')).toEqual([]);
  });
});

describe("the route-module convention", () => {
  it("sends an unsigned request for a registered page to sign-in, as the home page does, and runs no handler", async () => {
    const calls = { handled: 0 };
    const { app } = served({ pages: [fixturePage(calls)] });
    const res = await request(app).get("/_fixture/page");
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
    expect(res.text).not.toContain("Fixture rows");
    expect(calls.handled).toBe(0);
    // The control: the home page does the same, so the fixture's redirect is the convention's and not an accident.
    expect((await request(app).get("/")).headers["location"]).toBe(res.headers["location"]);
  });

  it("renders the page for a signed-in person, with its core content in the HTML (scripts off)", async () => {
    const calls = { handled: 0 };
    const { app } = served({ pages: [fixturePage(calls)] });
    const { cookie } = await signIn(app);
    const res = await request(app).get("/_fixture/page").set("Cookie", cookie);
    expect(res.status).toBe(200);
    expect(calls.handled).toBe(1);
    expect(res.text).toContain("<caption>Fixture rows</caption>");
    expect(res.text).toMatch(/<td>alpha<\/td><td>3<\/td>/);
    expect(res.text).toMatch(/<td>beta<\/td><td>5<\/td>/);
    expect(res.text).toMatch(/<form method="post" action="\/_fixture\/page">/);
    // HEAD of a GET page is answered too, by the same handler, with no body.
    const head = await request(app).head("/_fixture/page").set("Cookie", cookie);
    expect(head.status).toBe(200);
  });

  it("refuses a POST with no token, a wrong token, and no session, and runs no handler for any", async () => {
    const calls = { handled: 0 };
    const { app } = served({ pages: [fixturePage(calls)] });
    const { cookie, csrf } = await signIn(app);
    const noToken = await request(app).post("/_fixture/page").set("Cookie", cookie).type("form").send({});
    expect(noToken.status).toBe(403);
    const wrong = await request(app).post("/_fixture/page").set("Cookie", cookie).type("form").send({ _csrf: `${csrf}x` });
    expect(wrong.status).toBe(403);
    const unsigned = await request(app).post("/_fixture/page").type("form").send({ _csrf: csrf });
    expect(unsigned.status).toBe(403);
    expect(calls.handled).toBe(0);
    // The control: with the token it is carried out.
    const ok = await request(app).post("/_fixture/page").set("Cookie", cookie).type("form").send({ _csrf: csrf });
    expect(ok.status).toBe(303);
    expect(calls.handled).toBe(1);
  });

  it("answers a method the module did not list as a page that is not there, and runs no handler", async () => {
    const calls = { handled: 0 };
    const page = { ...fixturePage(calls), methods: ["GET"] as const };
    const { app } = served({ pages: [page] });
    const { cookie, csrf } = await signIn(app);
    // The control: the page is registered for GET, so the POST's 404 is the method's and not an absent page.
    expect((await request(app).get("/_fixture/page").set("Cookie", cookie)).status).toBe(200);
    expect(calls.handled).toBe(1);
    const res = await request(app).post("/_fixture/page").set("Cookie", cookie).type("form").send({ _csrf: csrf });
    expect(res.status).toBe(404);
    expect(calls.handled).toBe(1);
  });

  it("fails at start-up, in words, when two modules claim one path", () => {
    const a = fixturePage();
    const b = { ...fixturePage(), id: "studio-releases" };
    expect(() => served({ pages: [a, b], functionIds: new Set([a.id, b.id]) })).toThrow(
      /\/_fixture\/page.*studio-frame.*studio-releases|\/_fixture\/page.*studio-releases.*studio-frame/s,
    );
    // Two modules on one path, whatever their methods: a path belongs to one page.
    const c = { ...b, methods: ["POST"] as const };
    expect(() => served({ pages: [a, c], functionIds: new Set([a.id, c.id]) })).toThrow(/same path|one path|claim/i);
  });

  it("fails at start-up, in words, when an id is not a row of FUNCTIONS.yaml", () => {
    const page = { ...fixturePage(), id: "no-such-function-row" };
    expect(() => served({ pages: [page] })).toThrow(/no-such-function-row/);
    expect(() => served({ pages: [page] })).toThrow(/FUNCTIONS\.yaml/);
    // The check reads the real file: a real row's id is accepted, so the refusal above is not a blanket one.
    expect(() => served({ pages: [fixturePage()] })).not.toThrow();
  });

  it("fails at start-up when two modules share an id, or a path would shadow a route the server owns, or a method is not one", () => {
    const a = fixturePage();
    expect(() => served({ pages: [a, { ...a, path: "/_fixture/other" }] })).toThrow(/studio-frame.*(twice|once|same id|more than one)/is);
    for (const path of ["/", "/session/sign-in", "/session/callback", "/healthz", "/assets/pages/x", "/v1/anything"]) {
      expect(() => served({ pages: [{ ...a, path }] }), path).toThrow(new RegExp(path.replace(/\//g, "\\/")));
    }
    expect(() => served({ pages: [{ ...a, methods: ["TRACE" as never] }] })).toThrow(/TRACE/);
    expect(() => served({ pages: [{ ...a, methods: [] }] })).toThrow(/method/i);
  });

  it("reads the real FUNCTIONS.yaml: every id the convention can name is a row there, 47 of them", async () => {
    const { functionIdsFromFile } = await import("../../server/pages.js");
    const ids = functionIdsFromFile();
    const rows = [...readFileSync(join(PAGES, "FUNCTIONS.yaml"), "utf8").matchAll(/^ {2}- id: (\S+)\s*$/gm)].map((m) => m[1]);
    expect(ids.size).toBe(47);
    expect([...ids].sort()).toEqual([...rows].sort());
    expect(ids.has("studio-frame")).toBe(true);
  });
});

// -------------------------------------------------------------------------------------------- 3. the client-script bundle

describe("the asset build", () => {
  type Built = { manifest: Record<string, string>; outDir: string };
  type Builder = (options: { outDir: string; modulesDir?: string; extraStylesheets?: string[] }) => Promise<Built>;
  let buildAssets: Builder;
  let built: Built;
  let outDir = "";

  beforeAll(async () => {
    buildAssets = ((await import("../../scripts/assets.mjs")) as { buildAssets: Builder }).buildAssets;
    outDir = join(root, "built");
    built = await buildAssets({ outDir, modulesDir: join(FIXTURES, "modules") });
  }, 60_000);

  it("makes one hashed stylesheet from packages/design, with the tokens and the primitives in it", () => {
    const name = built.manifest["pages.css"] ?? "";
    expect(name).toMatch(/^pages-[A-Z0-9]{8}\.css$/);
    const css = readFileSync(join(outDir, name), "utf8");
    expect(css).toContain("--brass:"); // tokens.css
    expect(css).toMatch(/\.btn\b/); // primitives.css
    expect(css).toMatch(/\.skip-link\b/);
    expect(css).toContain("Atkinson Hyperlegible Next");
    expect(css).not.toMatch(/GDS Transport|govuk/i);
    // No folder of the pages tree holds a stylesheet of its own: the build reads packages/design and copies none of it.
    const own = [PAGES + "/tree-default", PAGES + "/modules", PAGES + "/server"].flatMap((f) =>
      existsSync(f) ? readdirSync(f, { recursive: true }).map(String).filter((n) => n.endsWith(".css")) : [],
    );
    expect(own).toEqual([]);
  });

  it("bundles a module to a hashed ES module that resolves the shared package's source and is lowered to ES2018", () => {
    const name = built.manifest["modules/fixture.ts"] ?? "";
    expect(name).toMatch(/^fixture-[A-Z0-9]{8}\.js$/);
    const js = readFileSync(join(outDir, name), "utf8");
    expect(js).toContain("intelligence mapping platform"); // PRODUCT_STATEMENT, from packages/glass-shared/src
    expect(js).toContain("getElementById");
    expect(js).not.toMatch(/\?\.|\?\?/); // the source uses both; ES2018 has neither
    expect(js).not.toMatch(/\brequire\(/);
    expect(js).not.toMatch(/react/i);
  });

  it("names a file by its content: the same input gives the same name, a changed one a different name", async () => {
    const again = await buildAssets({ outDir: join(root, "built-again"), modulesDir: join(FIXTURES, "modules") });
    expect(again.manifest).toEqual(built.manifest);
    const changed = join(root, "modules-changed");
    mkdirSync(changed, { recursive: true });
    writeFileSync(join(changed, "fixture.ts"), `${readFileSync(join(FIXTURES, "modules", "fixture.ts"), "utf8")}\ndocument.title += "!";\n`);
    const other = await buildAssets({ outDir: join(root, "built-changed"), modulesDir: changed });
    expect(other.manifest["modules/fixture.ts"]).not.toBe(built.manifest["modules/fixture.ts"]);
    expect(other.manifest["pages.css"]).toBe(built.manifest["pages.css"]);
  }, 60_000);

  it("writes a manifest the server can read, and every file it names is there", () => {
    const manifest = JSON.parse(readFileSync(join(outDir, "manifest.json"), "utf8")) as Record<string, string>;
    expect(manifest).toEqual(built.manifest);
    for (const file of Object.values(manifest)) expect(existsSync(join(outDir, file)), file).toBe(true);
  });

  it("refuses a module that imports React, in words", async () => {
    // Written here, not kept in the tree: a file that imports React under `apps/pages` is what `no_react_check.mjs` exists to refuse.
    const reactDir = join(root, "modules-react");
    mkdirSync(reactDir, { recursive: true });
    writeFileSync(join(reactDir, "importsReact.ts"), 'import { createElement } from "react";\ndocument.body.append(String(createElement("div")));\n');
    await expect(buildAssets({ outDir: join(root, "built-react"), modulesDir: reactDir })).rejects.toThrow(
      /react.*(ADR-152|not allowed|no React)/is,
    );
  }, 60_000);

  it("refuses a stylesheet that brings in GDS Transport, the GOV.UK tree's face", async () => {
    // The shape govuk-frontend writes its own face in: a listed family, a file under /assets/govuk/fonts/.
    const planted = join(root, "gds.css");
    writeFileSync(planted, '@font-face{font-family:"GDS Transport";font-weight:700;src:url("/assets/govuk/fonts/bold-b542beb274-v2.woff2") format("woff2")}\n');
    await expect(buildAssets({ outDir: join(root, "built-gds"), modulesDir: join(FIXTURES, "modules"), extraStylesheets: [planted] })).rejects.toThrow(
      /GDS Transport/,
    );
  }, 60_000);

  it("serves what it built: the stylesheet and the module through the real route, immutable", async () => {
    const { app } = build({ assets: { dir: outDir, manifest: built.manifest }, viewDirs: FIXTURE_VIEWS });
    for (const file of [built.manifest["pages.css"], built.manifest["modules/fixture.ts"]]) {
      const res = await request(app).get(`/assets/pages/${file}`);
      expect(res.status, file).toBe(200);
      expect(res.headers["cache-control"], file).toBe(IMMUTABLE);
    }
    // The manifest is the build's record and is not served.
    expect((await request(app).get("/assets/pages/manifest.json")).status).toBe(404);
  });
});
