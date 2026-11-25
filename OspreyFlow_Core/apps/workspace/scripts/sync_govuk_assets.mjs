// Copies the GOV.UK Frontend fonts and images into the Glass's own `public/` folder and writes a
// copy of its precompiled stylesheet, beside them, whose asset URLs point at them (ADR-132).
//
// Why: the deployment never calls out to a CDN (spec/00_ARCHITECTURE.md §7), so the fonts and
// images are served from the Glass's own origin under /assets/govuk/. The package's stylesheet
// refers to /assets/... absolutely, so its URLs are rewritten rather than recompiled from Sass.
// A package version that moves its URLs makes this script fail loudly, not ship broken fonts.
//
// **The GOV.UK identity switch (ADR-152 decision 14, invariant I9; the owner's ruling of 21 November 2026).**
// GDS Transport is licensed for services on GOV.UK domains only, so a default build holds none of it. The
// switch arrives as the environment variable `OSPREY_GOVUK_IDENTITY` (`1` or `true`: on; anything else, or
// unset: off), which is the workspace image's build argument of the same name, which the renderer passes
// only for a deployment whose `appearance.govuk_identity` is on. Off, this writes no font and no image, and a
// copy of the stylesheet with the face's `@font-face` rules, the family name and the crest taken out, so the
// GOV.UK look falls back to arial and draws no crown (a fallback, never a request for a missing file). On, as it
// was. `tests/glass_trees/test_default_build_holds_no_gds_transport.py` runs it both ways.
import console from "node:console";
import { createRequire } from "node:module";
import process from "node:process";
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const PREFIX = "url(/assets/";
const REWRITTEN = "url(/assets/govuk/";

/** Rewrite every `url(/assets/` to `url(/assets/govuk/`; returns the CSS and the count rewritten. */
export function rewriteAssetUrls(css) {
  let count = 0;
  const out = css.replace(/url\(\/assets\/(?!govuk\/)/g, () => {
    count += 1;
    return REWRITTEN;
  });
  return { css: out, count };
}

/** Whether the deployment's GOV.UK identity is on for this build: `1` or `true` (any case), nothing else. */
export function identityOn(env) {
  return ["1", "true"].includes(String(env.OSPREY_GOVUK_IDENTITY ?? "").trim().toLowerCase());
}

const FACE_RULE = /@font-face\{[^}]*font-family:GDS Transport[^}]*\}/g;
const FACE_IN_STACK = /(font-family:)GDS Transport,/g;
const CREST_DECLARATION = /(?:-webkit-)?(?:mask-image|background-image):url\(\/assets\/images\/govuk-crest\.svg\);?/g;
/** What must be gone from the stylesheet of a build with the identity off. */
const LEFT_OVER = /GDS Transport|govuk-crest|url\(\/assets\//;

/** The stylesheet for a build with the identity off: GOV.UK Frontend's own, without its `@font-face` rules, without
 * the family in any font stack (the stacks fall back to `arial,sans-serif`) and without the declarations that draw
 * the crest. Returns the CSS and the number of face rules removed (the caller fails if there were none: the package
 * has moved its rules). Everything else is untouched. */
export function withoutGdsTransport(css) {
  let faces = 0;
  const out = css
    .replace(FACE_RULE, () => {
      faces += 1;
      return "";
    })
    .replace(FACE_IN_STACK, "$1")
    .replace(CREST_DECLARATION, "");
  return { css: out, faces };
}

/** The family named at the head of a font stack, as the package writes every one of them. */
const STACK_HEAD = /(font-family:)GDS Transport,/g;

/** For a build with the identity on: the face is named only in the `@font-face` rules and `--govuk-typeface`, never at the
 * head of a stack. Each stack becomes `font-family:var(--govuk-typeface,)arial,sans-serif`: the variable is defined only
 * by `[data-govuk-typeface="on"]` (`packages/design/tokens.css`), which the page carries only with the switch on and on
 * a gov.uk address (GDS Transport's licence, ADR-152 Amendment 2 item 3), so at any other address the package's own
 * components draw in arial, as `--ui` does. Returns the CSS and the number of stacks changed. */
export function gateTypefaceOnTheAddress(css) {
  let stacks = 0;
  const out = css.replace(STACK_HEAD, (_all, head) => {
    stacks += 1;
    return `${head}var(--govuk-typeface,)`;
  });
  return { css: out, stacks };
}

/** Number of `url(/assets/` occurrences that do not begin `url(/assets/govuk/`. */
function strayCount(css) {
  return css.split(PREFIX).length - 1 - (css.split(REWRITTEN).length - 1);
}

function countFiles(dir) {
  let n = 0;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    n += statSync(p).isDirectory() ? countFiles(p) : 1;
  }
  return n;
}

/** Beside the fonts (when there are any), served as a file of its own: not bundled (Vite's minifier refuses the
 * package's stylesheet), outside `src/` so the design gates do not read it, and fetched only by a GOV.UK page. */
function writeStylesheet(outDir, css, version, note) {
  mkdirSync(outDir, { recursive: true });
  const more = note ? ` (${note})` : "";
  const banner = `/* GENERATED by scripts/sync_govuk_assets.mjs from govuk-frontend ${version}${more}. Do not edit. */\n`;
  // `@charset` is honoured only as the very first thing in a file, so the banner goes after it.
  const charset = /^@charset "[^"]+";/.exec(css)?.[0] ?? "";
  writeFileSync(join(outDir, "govuk-frontend.css"), charset + "\n" + banner + css.slice(charset.length));
}

function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const app = resolve(here, "..");
  const cssPath = createRequire(import.meta.url).resolve("govuk-frontend/dist/govuk/govuk-frontend.min.css");
  const distGovuk = dirname(cssPath);
  const pkg = JSON.parse(readFileSync(join(distGovuk, "..", "..", "package.json"), "utf8"));

  const identity = identityOn(process.env);
  const target = join(app, "public", "assets", "govuk");
  // Always cleared first: a build with the identity off must not keep the files an earlier one wrote.
  rmSync(target, { recursive: true, force: true });
  const filter = (src) => !/(^|[\\/])Icon\r$/.test(src);
  if (identity) {
    for (const sub of ["fonts", "images"]) {
      cpSync(join(distGovuk, "assets", sub), join(target, sub), { recursive: true, filter });
    }
  }
  const copied = identity ? countFiles(target) : 0;

  const raw = readFileSync(cssPath, "utf8");
  if (!identity) {
    const { css: plain, faces } = withoutGdsTransport(raw);
    if (faces === 0 || LEFT_OVER.test(plain)) {
      console.error(
        `sync_govuk_assets: govuk-frontend ${pkg.version} stylesheet did not lose GDS Transport cleanly ` +
          `(${faces} face rules removed; the family, the crest or an asset URL remains). ` +
          "The package has moved its rules; update this script.",
      );
      process.exit(1);
    }
    writeStylesheet(target, plain, pkg.version, "the GOV.UK identity is off: no typeface rules, no crest");
    console.log(`sync_govuk_assets: identity off, stylesheet only (govuk-frontend ${pkg.version}, ${faces} face rules removed)`);
    return;
  }
  const { css: rewritten, count } = rewriteAssetUrls(raw);
  const { css, stacks } = gateTypefaceOnTheAddress(rewritten);
  if (count === 0 || strayCount(css) > 0 || stacks === 0 || /font-family:GDS Transport,/.test(css)) {
    console.error(
      `sync_govuk_assets: govuk-frontend ${pkg.version} stylesheet did not rewrite cleanly ` +
        `(${count} rewritten, ${strayCount(css)} un-rewritten url(/assets/ remaining, ${stacks} font stacks gated on the address). ` +
        "The package has moved its asset URLs; update this script.",
    );
    process.exit(1);
  }
  writeStylesheet(target, css, pkg.version, "the typeface gated on a gov.uk address");
  console.log(`sync_govuk_assets: ${copied} files copied, ${count} URLs rewritten, ${stacks} font stacks gated (govuk-frontend ${pkg.version})`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) main();
