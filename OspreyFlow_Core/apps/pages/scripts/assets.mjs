// The pages service's browser assets (ADR-152 decisions 6, 7 and 8): one stylesheet and the client modules, written to a
// folder with content-hashed names and a manifest, which the service serves at /assets/pages/* and links from its layout.
//
//   node scripts/assets.mjs --out <folder> [--modules <folder>]
//
// The stylesheet is `packages/design`'s own files, bundled: `tokens.css` and `primitives.css` (which imports `scale.css`
// and `panelType.css`), the same two the workspace imports, and the faces `packages/design/fonts.json` names for the
// Default tree. None of their rules is copied into this folder. The GOV.UK brand's rules (`[data-brand="govuk"]`) are left
// out of the Default tree's stylesheet, and with them the one place `tokens.css` names the GOV.UK face: that face is the
// GOV.UK tree's, with two conditions of its own (ADR-152 Amendment 2), and the Default tree never loads or serves it. Which
// face, and where its files are self-hosted, is read from `fonts.json` (the entries that carry a condition), never written here.
//
// A module is a `.ts` file directly in `modules/`. It is bundled to one ES module (no splitting), lowered to ES2018 (decision
// 2), minified, with no source map. It may import `packages/glass-shared` (plain TypeScript): the workspace link in
// `node_modules/@ospreyflow/glass-shared` points at the package, whose `exports` name `src/index.ts`, so esbuild reads that
// source directly and nothing is built or published first. It may not import React (invariant I1), and, until a slice that
// draws allows one by name below, no drawing library (decision 9: the shared package imports none either).
//
// The built output is checked before it is accepted: a stylesheet or module that carries the GOV.UK face, or a path under
// the folder it is self-hosted in, fails the build in words.
import { build } from "esbuild";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PAGES = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CORE = resolve(PAGES, "..", "..");
const DESIGN = join(CORE, "packages", "design");

/** The drawing libraries a module may import. Empty until the first slice that draws names its library here (ADR-152 decision 9). */
export const ALLOWED_DRAWING = [];
const REACT = /^(react|react-dom|scheduler)(\/|$)/;
const DRAWING = /^(sigma|@sigma\/.+|maplibre-gl)(\/|$)/;
const FONT_LIST = JSON.parse(readFileSync(join(DESIGN, "fonts.json"), "utf8"));

/** The entries the list conditions on the GOV.UK identity: the other tree's faces, never the Default tree's. */
function conditioned(list) {
  return list.fonts.filter((entry) => "only_when" in entry || "only_on" in entry);
}

/**
 * What the Default tree never loads or serves: a conditioned face by name (its words apart by any run of space, hyphen or
 * underscore) and anything under the folder the list says it is self-hosted in. Read from the list, so it names what the list names.
 */
export function identityPattern(list) {
  const escape = (text) => text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  const names = conditioned(list).flatMap((entry) => [
    entry.family.split(/\s+/).map(escape).join("[\\s_-]*"),
    ...(entry.self_hosted_under ? [escape(entry.self_hosted_under.replace(/\/+$/, "") + "/")] : []),
  ]);
  return names.length === 0 ? /(?!)/ : new RegExp(names.join("|"), "i");
}

const GOVUK_IDENTITY = identityPattern(FONT_LIST);
const GOVUK_BRAND = /\[\s*data-brand\s*=\s*["']?govuk["']?\s*\]/i;

/** The Default tree's faces: every `fonts.json` entry that is an `@fontsource` package and carries no condition of its own. */
export function defaultFaces(list) {
  return list.fonts.filter((entry) => !("only_when" in entry) && !("only_on" in entry) && entry.source.startsWith("@fontsource/"));
}

// ------------------------------------------------------------------------------------- leaving the GOV.UK brand out

function blankComments(css) {
  let out = "";
  for (let i = 0; i < css.length; ) {
    const c = css[i];
    if (c === "/" && css[i + 1] === "*") {
      const end = css.indexOf("*/", i + 2);
      i = end === -1 ? css.length : end + 2;
    } else if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < css.length && css[j] !== c) j += css[j] === "\\" ? 2 : 1;
      out += css.slice(i, j + 1);
      i = j + 1;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

/** Splits at a character that is not inside parentheses, brackets or a string. */
function splitTop(text, separator) {
  const parts = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'") {
      i += 1;
      while (i < text.length && text[i] !== c) i += text[i] === "\\" ? 2 : 1;
    } else if (c === "(" || c === "[") depth += 1;
    else if (c === ")" || c === "]") depth -= 1;
    else if (c === separator && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  return parts;
}

/** The index of the `}` that closes the `{` at `open`. */
function closing(css, open) {
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    const c = css[i];
    if (c === '"' || c === "'") {
      i += 1;
      while (i < css.length && css[i] !== c) i += css[i] === "\\" ? 2 : 1;
    } else if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  throw new Error("a stylesheet has a block that is never closed");
}

const GROUPING = /^@(media|supports|layer|container|document)\b/i;

function dropGovuk(css) {
  let out = "";
  let i = 0;
  while (i < css.length) {
    const brace = css.indexOf("{", i);
    const semicolon = css.indexOf(";", i);
    if (brace === -1 || (semicolon !== -1 && semicolon < brace)) {
      const end = semicolon === -1 ? css.length : semicolon + 1;
      out += css.slice(i, end);
      i = end;
      continue;
    }
    const prelude = css.slice(i, brace).trim();
    const end = closing(css, brace);
    const body = css.slice(brace + 1, end);
    i = end + 1;
    if (prelude.startsWith("@")) {
      if (!GROUPING.test(prelude)) {
        out += `${prelude}{${body}}\n`;
        continue;
      }
      const inner = dropGovuk(body);
      if (inner.trim() !== "") out += `${prelude}{${inner}}\n`;
      continue;
    }
    const kept = splitTop(prelude, ",").filter((selector) => !GOVUK_BRAND.test(selector));
    if (kept.length > 0) out += `${kept.map((s) => s.trim()).join(", ")}{${body}}\n`;
  }
  return out;
}

/** The Default tree's view of one of `packages/design`'s stylesheets: the same rules, less the GOV.UK brand's. */
export function withoutGovukBrand(css) {
  return dropGovuk(blankComments(css));
}

// ------------------------------------------------------------------------------------------------ the build's own rules

function refuseIdentity(text, where) {
  const found = GOVUK_IDENTITY.exec(text);
  if (found) {
    throw new Error(
      `${where} carries "${found[0]}": ${conditioned(FONT_LIST).map((e) => e.family).join(" and ")} and the files self-hosted for it are the GOV.UK tree's, never the Default tree's (ADR-152 Amendment 2, invariant I9)`,
    );
  }
}

function rulesPlugin() {
  return {
    name: "pages-rules",
    setup(b) {
      b.onResolve({ filter: /.*/ }, (args) => {
        if (args.kind === "entry-point" || args.path.startsWith(".") || args.path.startsWith("/")) return undefined;
        if (REACT.test(args.path)) {
          return {
            errors: [{ text: `${args.path} is imported by ${relative(CORE, args.importer)}: React is not allowed in a pages bundle (ADR-152 invariant I1, no React in apps/pages or packages/glass-shared)` }],
          };
        }
        if (DRAWING.test(args.path) && !ALLOWED_DRAWING.includes(args.path.split("/")[0])) {
          return {
            errors: [{ text: `${args.path} is imported by ${relative(CORE, args.importer)}: a drawing library is not bundled until a slice that draws allows it by name in scripts/assets.mjs (ADR-152 decision 9)` }],
          };
        }
        return undefined;
      });
      b.onLoad({ filter: /\.css$/, namespace: "file" }, (args) => {
        let text = readFileSync(args.path, "utf8");
        // Only the design package's own files are the Default tree's to filter; any other stylesheet is taken whole, and refused if it names the other tree's face.
        if (args.path.startsWith(`${DESIGN}/`)) text = withoutGovukBrand(text);
        refuseIdentity(text, relative(CORE, args.path));
        return { contents: text, loader: "css", resolveDir: dirname(args.path) };
      });
    },
  };
}

/** The stylesheet's entry: a file that exists only in the build, importing the design files and the Default tree's faces. */
function stylesheetEntry(extraStylesheets) {
  const faces = defaultFaces(FONT_LIST).flatMap((entry) => entry.weights.map((weight) => `${entry.source}/${weight}.css`));
  const lines = [join(DESIGN, "tokens.css"), join(DESIGN, "primitives.css")].map((path) => `@import ${JSON.stringify(path)};`);
  lines.push(...faces.map((spec) => `@import ${JSON.stringify(spec)};`));
  lines.push(...extraStylesheets.map((path) => `@import ${JSON.stringify(resolve(path))};`));
  return lines.join("\n");
}

function moduleEntries(modulesDir) {
  if (!existsSync(modulesDir)) return [];
  const names = readdirSync(modulesDir);
  const jsx = names.filter((name) => /\.[jt]sx$/.test(name));
  if (jsx.length > 0) throw new Error(`${jsx.join(", ")} in modules/: a module is a plain .ts file, with no JSX (ADR-152 invariant I1, no React)`);
  return names.filter((name) => name.endsWith(".ts") && !name.endsWith(".d.ts") && !/\.(test|spec)\.ts$/.test(name)).sort();
}

/**
 * Builds the assets into `outDir` (emptied first) and returns `{ manifest, outDir }`. `manifest` maps `pages.css` and
 * `modules/<name>.ts` to the content-hashed file written for each, relative to `outDir`; the same record is written there as
 * `manifest.json`, which the service reads and does not serve.
 */
export async function buildAssets({ outDir, modulesDir = join(PAGES, "modules"), extraStylesheets = [] }) {
  const out = resolve(outDir);
  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });
  const modules = moduleEntries(modulesDir);
  const entryContents = stylesheetEntry(extraStylesheets);
  const virtual = {
    name: "pages-stylesheet-entry",
    setup(b) {
      b.onResolve({ filter: /^pages-stylesheet-entry$/ }, () => ({ path: "pages.css", namespace: "pages-entry" }));
      b.onLoad({ filter: /.*/, namespace: "pages-entry" }, () => ({ contents: entryContents, loader: "css", resolveDir: DESIGN }));
    },
  };
  let result;
  try {
    result = await build({
      absWorkingDir: CORE,
      entryPoints: { pages: "pages-stylesheet-entry", ...Object.fromEntries(modules.map((name) => [basename(name, ".ts"), join(resolve(modulesDir), name)])) },
      outdir: out,
      entryNames: "[name]-[hash]",
      // A font is named for its content by the folder it sits in, so its own name stays what `@fontsource` gives it, which
      // `tests/glass_trees/test_fonts_list.py` reads the family, weight and style from.
      assetNames: "fonts/[hash]/[name]",
      loader: { ".woff2": "file", ".woff": "file" },
      bundle: true,
      format: "esm",
      target: "es2018",
      platform: "browser",
      minify: true,
      sourcemap: false,
      splitting: false,
      metafile: true,
      logLevel: "silent",
      plugins: [rulesPlugin(), virtual],
      nodePaths: [join(CORE, "node_modules")],
    });
  } catch (error) {
    const text = Array.isArray(error?.errors) && error.errors.length > 0 ? error.errors.map((e) => e.text).join("; ") : String(error?.message ?? error);
    throw new Error(`the pages assets could not be built: ${text}`, { cause: error });
  }
  const manifest = {};
  for (const [file, info] of Object.entries(result.metafile.outputs)) {
    const name = relative(out, resolve(CORE, file)).split("\\").join("/");
    if (!info.entryPoint) continue;
    if (name.endsWith(".css")) manifest["pages.css"] = name;
    else if (name.endsWith(".js")) {
      const source = modules.find((m) => name.startsWith(`${basename(m, ".ts")}-`));
      if (source) manifest[`modules/${source}`] = name;
    }
  }
  // What was written is checked, not only what went in: a face or a path that arrived another way still fails here.
  for (const file of Object.keys(result.metafile.outputs)) {
    const path = resolve(CORE, file);
    refuseIdentity(path.split("\\").join("/"), relative(out, path));
    if (/\.(css|js)$/.test(path)) refuseIdentity(readFileSync(path, "utf8"), relative(out, path));
  }
  if (!manifest["pages.css"]) throw new Error("the pages assets were built without a stylesheet");
  const sorted = Object.fromEntries(Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(join(out, "manifest.json"), `${JSON.stringify(sorted, null, 2)}\n`);
  return { manifest: sorted, outDir: out };
}

function argument(name) {
  const at = process.argv.indexOf(name);
  return at === -1 ? undefined : process.argv[at + 1];
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const outDir = argument("--out");
  if (!outDir) {
    console.error("usage: node scripts/assets.mjs --out <folder> [--modules <folder>]");
    process.exit(2);
  }
  try {
    const { manifest } = await buildAssets({ outDir, ...(argument("--modules") ? { modulesDir: argument("--modules") } : {}) });
    console.log(`pages assets: ${Object.keys(manifest).length} entries in ${outDir}`);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
