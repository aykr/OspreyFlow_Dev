// Invariant I9, in a real browser (slice PL7c; ADR-152 decision 14 and Amendment 2 item 3; the owner's ruling of 21 November
// 2026): the GOV.UK identity is the crown, the GOV.UK logotype and GDS Transport, and they show only when the switch
// (`appearance.govuk_identity`) is on; the crown only on a gov.uk address; GDS Transport (licensed for services on GOV.UK
// domains only) only with the switch on **and** on a gov.uk address.
//
// What the page is made of is the real thing, not a copy of it: `packages/design/tokens.css`; the GOV.UK Frontend
// stylesheet and fonts as `apps/workspace/scripts/sync_govuk_assets.mjs` writes them, run here once with the switch off (a
// default build) and once with it on; the page's marks from `applyBrand` in `packages/glass-shared`, bundled; and the header
// and footer from `harness/govuk_chrome.js`, the sign-in page's own script. The browser is told the page is at a gov.uk
// address or not by request interception (no network is used), so `window.location.hostname` is the real thing the code reads.
//
// What is read: every element's computed font family (the rule's own words: "no `GDS Transport` in any computed font"), the
// header's logotype and crown by their own markup, and every request the page made (a default build must ask for no face).
//
//   npm run test:govuk --workspace apps/pages        (not yet in `make ci`: its wiring is the owner's diff)
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE = resolve(HERE, "..", "..", "..", "..");
const WORKSPACE_SCRIPT = join(CORE, "apps", "workspace", "scripts", "sync_govuk_assets.mjs");

const GOV_UK = "https://service.gov.uk";
const ELSEWHERE = "https://other.example.test";

const TYPES: Record<string, string> = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml" };

/** What `sync_govuk_assets.mjs` writes under `public/assets/govuk/`, for a build with the switch as given (run in a scratch
 * copy of the folder with `node_modules` linked, so the checkout is never written to). */
function syncedAssets(scratch: string, switchOn: boolean): string {
  const app = join(scratch, "apps", "workspace");
  mkdirSync(join(app, "scripts"), { recursive: true });
  cpSync(WORKSPACE_SCRIPT, join(app, "scripts", "sync_govuk_assets.mjs"));
  symlinkSync(join(CORE, "node_modules"), join(scratch, "node_modules"));
  const env = { ...process.env };
  delete env["OSPREY_GOVUK_IDENTITY"];
  if (switchOn) env["OSPREY_GOVUK_IDENTITY"] = "1";
  execFileSync(process.execPath, [join("scripts", "sync_govuk_assets.mjs")], { cwd: app, env, stdio: "pipe" });
  return join(app, "public");
}

let defaultBuild = "";
let identityBuild = "";
let brandScript = "";

test.beforeAll(async () => {
  const scratch = mkdtempSync(join(tmpdir(), "ospreyflow-pages-govuk-"));
  defaultBuild = syncedAssets(join(scratch, "default"), false);
  identityBuild = syncedAssets(join(scratch, "identity"), true);
  const bundled = await build({
    entryPoints: [join(CORE, "packages", "glass-shared", "src", "brand", "brand.ts")],
    bundle: true,
    write: false,
    format: "iife",
    globalName: "OspreyBrand",
    target: "es2018",
  });
  brandScript = bundled.outputFiles[0]!.text;
});

interface Visit {
  /** Every path the page asked for. */
  requested: string[];
  /** Every distinct computed `font-family` of any element, as the browser resolved it. */
  families: string[];
  /** The header's own markup facts. */
  logotype: number;
  crown: number;
  headerText: string;
}

/** Opens the page at `origin` with the build's assets (`build`: `defaultBuild` or `identityBuild`), the brand and the switch as
 * given, and reads what it drew. The head carries `tokens.css` and the stylesheet; the body is the sign-in page's shape
 * (`main#kc-form-login`), which `govuk_chrome.js` wraps in the header and footer. */
async function visit(page: Page, origin: string, assets: string, brand: "govuk" | "ospreyflow", identity: boolean): Promise<Visit> {
  const requested: string[] = [];
  const page_ = `<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>x</title>
    <link rel="stylesheet" href="/tokens.css"><link rel="stylesheet" href="/assets/govuk/govuk-frontend.css">
    <style>body{font-family:var(--ui)}</style></head>
    <body><main id="kc-form-login"><h1 class="govuk-heading-l">Sign in</h1><p class="govuk-body">Words.</p></main>
    <script src="/brand.js"></script>
    <script>OspreyBrand.applyBrand(${JSON.stringify(brand)}, ${identity});
      window.OSPREY_GOVUK = { serviceName: "Test service", organisation: "A department", phase: "beta", glassOrigin: "", ${identity ? "govukIdentity: true" : ""} };</script>
    <script src="/govuk_chrome.js"></script></body></html>`;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    requested.push(url.pathname);
    const send = (body: string | Buffer, path: string) => route.fulfill({ status: 200, contentType: TYPES[extname(path)] ?? "text/plain", body });
    if (url.pathname === "/") return send(page_, "x.html").then(() => undefined);
    if (url.pathname === "/tokens.css") return send(readFileSync(join(CORE, "packages", "design", "tokens.css")), "x.css");
    if (url.pathname === "/brand.js") return send(brandScript, "x.js");
    if (url.pathname === "/govuk_chrome.js") return send(readFileSync(join(CORE, "harness", "govuk_chrome.js")), "x.js");
    const file = join(assets, url.pathname);
    if (url.pathname.startsWith("/assets/govuk/") && existsSync(file)) return send(readFileSync(file), file);
    return route.fulfill({ status: 404, body: "" });
  });
  await page.goto(`${origin}/`);
  await page.evaluate("document.fonts.ready");
  // As text, so the browser's own globals need no DOM typing in this folder's compile.
  const seen = (await page.evaluate(`({
    families: [...new Set(Array.from(document.querySelectorAll("*")).map((el) => getComputedStyle(el).fontFamily))],
    logotype: document.querySelectorAll(".govuk-header__logotype").length,
    crown: document.querySelectorAll('circle[cx="20"][cy="17.6"]').length,
    headerText: (document.querySelector(".govuk-header") || { textContent: "" }).textContent.trim(),
  })`)) as Pick<Visit, "families" | "logotype" | "crown" | "headerText">;
  // The crown is the first drawing in the header's logotype and in the footer: a circle at (20, 17.6).
  return { requested, ...seen };
}

const namesGdsTransport = (v: Visit) => v.families.some((f) => f.includes("GDS Transport"));
const askedForAFace = (v: Visit) => v.requested.some((p) => /\/fonts\/|\.woff2?$/.test(p));

test.describe("the GOV.UK identity, in a browser (I9)", () => {
  for (const [name, origin] of [["on a gov.uk address", GOV_UK], ["off gov.uk", ELSEWHERE]] as const) {
    test(`switch off, ${name}: no logotype, no crown, no GDS Transport in any computed font, no request for a face`, async ({ page }) => {
      const v = await visit(page, origin, defaultBuild, "govuk", false);
      expect(v.logotype).toBe(0);
      expect(v.crown).toBe(0);
      expect(namesGdsTransport(v)).toBe(false);
      expect(askedForAFace(v)).toBe(false);
      // The header carries the department's name in the logo's place (decision 14), and the page's type is the fallback.
      expect(v.headerText).toContain("A department");
      expect(v.families.some((f) => f.includes("arial"))).toBe(true);
    });
  }

  test("switch on, off gov.uk: the logotype, no crown and no GDS Transport (the licence is for gov.uk domains)", async ({ page }) => {
    const v = await visit(page, ELSEWHERE, identityBuild, "govuk", true);
    expect(v.logotype).toBe(1);
    expect(v.crown).toBe(0);
    expect(namesGdsTransport(v)).toBe(false);
    expect(askedForAFace(v)).toBe(false);
  });

  test("switch on, on a gov.uk address: the logotype, the crown and GDS Transport, loaded", async ({ page }) => {
    const v = await visit(page, GOV_UK, identityBuild, "govuk", true);
    expect(v.logotype).toBe(1);
    expect(v.crown).toBeGreaterThan(0);
    expect(namesGdsTransport(v)).toBe(true);
    expect(await page.evaluate(`document.fonts.check('19px "GDS Transport"')`)).toBe(true);
    expect(await page.evaluate(`getComputedStyle(document.querySelector(".govuk-body")).fontFamily`)).toContain("GDS Transport");
    expect(await page.evaluate(`getComputedStyle(document.body).fontFamily`)).toContain("GDS Transport");
    expect(askedForAFace(v)).toBe(true);
  });

  test("a build that holds the face, with the switch off at run time, still draws none of it, even on gov.uk", async ({ page }) => {
    const v = await visit(page, GOV_UK, identityBuild, "govuk", false);
    expect(v.logotype).toBe(0);
    expect(v.crown).toBe(0);
    expect(namesGdsTransport(v)).toBe(false);
    expect(askedForAFace(v)).toBe(false);
  });

  test("the switch means nothing under the OspreyFlow brand, even on gov.uk", async ({ page }) => {
    const v = await visit(page, GOV_UK, identityBuild, "ospreyflow", true);
    expect(v.logotype).toBe(0);
    expect(v.crown).toBe(0);
    expect(namesGdsTransport(v)).toBe(false);
  });
});
