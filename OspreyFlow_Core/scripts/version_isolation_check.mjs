// ADR-152 invariant I13: the shared package imports no `sigma`, `@sigma/*` or `maplibre-gl`; and each front end's
// bundle holds the drawing libraries only at the versions its own manifest asks for.
//
//   node scripts/version_isolation_check.mjs [root]      root defaults to the checkout this script is in
//
// Started from the owner's evidence copy (`ospreyflow_maplibre_sigma_2026-11-18/evidence/version_isolation_check.mjs`,
// shown red and green on 18 November 2026) and changed where that copy did not fit this tree:
//   * it bundles with esbuild; this tree is built by Vite 8, so it bundles with the same bundler (`rolldown`)
//     through `scripts/lib/glass_trees.mjs`, and sees what the build sees;
//   * its entries were `src/main.js`; the workspace's is `apps/workspace/src/main.tsx`, and the shared package's is
//     every source file of `packages/glass-shared/src` that is not a test (so a file the index does not export
//     is still looked at; `src/index.ts` is among them);
//   * its pins were written into the script; here each is read from the tree's own `package.json`, so a change of
//     range there is a change of what the check demands, and no second list can drift.
//
// What this cannot see: a bundler drops an import used only as a type (`import type { Map } from "maplibre-gl"`),
// so a type-only import never reaches the bundle. That half is the `no-restricted-imports` block for
// `packages/glass-shared/**` in `eslint.config.js` (`allowTypeImports: false`), shown red in
// `OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py`.
//
// Exit 0 and "PASS", or exit 1 and "FAIL" with one line for each finding. A tree whose entry is missing fails: a
// check with nothing to bundle must not pass.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { TEST_FILE, packageDirectoryOf, reachedModulesOrFail, walk } from "./lib/glass_trees.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const root = resolve(process.argv[2] ?? join(HERE, ".."));

// The drawing libraries (D46). `graphology` is not one: both front ends may use it.
const RENDERER = /^(sigma|@sigma\/[^/]+|maplibre-gl)$/;

const failures = [];

// A range, as `package.json` writes one: `^3.0.0`, `~1.2.3`, `>=6.4.1 <7`, `1.2.3`, `3.x`, `*`, or any of those
// joined by `||`. Enough for the ranges this tree's manifests use; a range it cannot read is a failure, not a pass.
function parseVersion(text) {
  const match = /^v?(\d+)(?:\.(\d+|x|\*))?(?:\.(\d+|x|\*))?(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$/.exec(text.trim());
  if (!match) return null;
  const number = (part) => (part === undefined || part === "x" || part === "*" ? null : Number(part));
  return { major: Number(match[1]), minor: number(match[2]), patch: number(match[3]), pre: match[4] ?? null };
}

function compare(a, b) {
  for (const key of ["major", "minor", "patch"]) {
    const difference = (a[key] ?? 0) - (b[key] ?? 0);
    if (difference !== 0) return difference;
  }
  if (a.pre === b.pre) return 0;
  if (a.pre === null) return 1;
  if (b.pre === null) return -1;
  return a.pre < b.pre ? -1 : 1;
}

function comparatorsOf(token) {
  const bounded = /^(\^|~|>=|<=|>|<|=)?\s*(.+)$/.exec(token);
  if (!bounded) return null;
  const [, operator = "=", rest] = bounded;
  const version = parseVersion(rest);
  if (!version) return null;
  const floor = { major: version.major, minor: version.minor ?? 0, patch: version.patch ?? 0, pre: version.pre };
  const above = (major, minor, patch) => ({ major, minor, patch, pre: "" });
  switch (operator) {
    case "^": {
      const ceiling =
        version.major > 0 || version.minor === null
          ? above(version.major + 1, 0, 0)
          : version.minor > 0 || version.patch === null
            ? above(0, version.minor + 1, 0)
            : above(0, 0, (version.patch ?? 0) + 1);
      return [(v) => compare(v, floor) >= 0, (v) => compare(v, ceiling) < 0];
    }
    case "~": {
      const ceiling = version.minor === null ? above(version.major + 1, 0, 0) : above(version.major, version.minor + 1, 0);
      return [(v) => compare(v, floor) >= 0, (v) => compare(v, ceiling) < 0];
    }
    case ">=":
      return [(v) => compare(v, floor) >= 0];
    case ">":
      return [(v) => compare(v, floor) > 0];
    case "<=":
      return [(v) => compare(v, floor) <= 0];
    case "<":
      return [(v) => compare(v, floor) < 0];
    default: {
      // `=` or a bare version: a wildcard part means any value there.
      if (version.minor === null) return [(v) => v.major === version.major];
      if (version.patch === null) return [(v) => v.major === version.major && v.minor === version.minor];
      return [(v) => compare(v, floor) === 0];
    }
  }
}

/** True, false, or null when the range is not one this can read. */
function satisfies(versionText, rangeText) {
  const version = parseVersion(versionText);
  if (!version) return null;
  const range = rangeText.trim();
  if (range === "" || range === "*" || range === "latest") return true;
  for (const alternative of range.split("||")) {
    const tokens = alternative.trim().replace(/(>=|<=|>|<|=|\^|~)\s+/g, "$1").split(/\s+/).filter(Boolean);
    const tests = [];
    let readable = tokens.length > 0;
    for (const token of tokens) {
      const parts = comparatorsOf(token);
      if (parts === null) readable = false;
      else tests.push(...parts);
    }
    if (!readable) return null;
    if (tests.every((test) => test(version))) return true;
  }
  return false;
}

function readManifest(directory) {
  const path = join(root, directory, "package.json");
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf8"));
}

function declaredRenderers(manifest) {
  const declared = new Map();
  for (const kind of ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]) {
    for (const [name, range] of Object.entries(manifest?.[kind] ?? {})) {
      if (RENDERER.test(name) && !declared.has(name)) declared.set(name, range);
    }
  }
  return declared;
}

function versionOf(directory) {
  return JSON.parse(readFileSync(join(directory, "package.json"), "utf8")).version;
}

/** The drawing-library packages a set of bundled modules belong to: `name@version` -> the module that showed it. */
function rendererPackages(modules) {
  const found = new Map();
  for (const id of modules) {
    const owner = packageDirectoryOf(id);
    if (!owner || !RENDERER.test(owner.name)) continue;
    let version;
    try {
      version = versionOf(owner.directory);
    } catch {
      continue;
    }
    const key = `${owner.name}@${version}`;
    if (!found.has(key)) found.set(key, { name: owner.name, version, module: id });
  }
  return found;
}

// A front end: its bundle may hold a drawing library only at a version its own manifest allows.
async function checkFrontEnd(directory, entries, { required }) {
  const manifest = readManifest(directory);
  if (manifest === null) {
    if (required) failures.push(`${directory} has no package.json`);
    return;
  }
  const missing = entries.filter((entry) => !existsSync(join(root, directory, entry)));
  if (missing.length) {
    failures.push(`${directory}: entry not found: ${missing.join(", ")} (nothing to bundle, so nothing is checked)`);
    return;
  }
  const modules = await reachedModulesOrFail(root, entries.map((entry) => join(root, directory, entry)), directory, failures);
  if (modules === null) return;
  const found = rendererPackages(modules);
  const declared = declaredRenderers(manifest);
  console.log(directory, [...found.keys()].sort().join(" ") || "(no drawing library)");
  for (const { name, version, module } of found.values()) {
    const range = declared.get(name);
    if (range === undefined) continue; // a package another one brings (`@sigma/utils`), not one this tree pins
    const ok = satisfies(version, range);
    if (ok === null) failures.push(`${directory}: cannot read the range "${range}" that package.json gives ${name}`);
    else if (!ok) failures.push(`${directory}: bundles ${name}@${version}, package.json asks for ${range} (${relative(root, module)})`);
  }
}

// The shared package: no drawing library at all.
async function checkSharedPackage() {
  const directory = "packages/glass-shared";
  const sources = walk(join(root, directory, "src"), (path) => /\.[cm]?[jt]sx?$/.test(path) && !TEST_FILE.test(path));
  if (sources.length === 0) {
    failures.push(`${directory}/src has no source file to bundle (nothing to bundle, so nothing is checked)`);
    return;
  }
  const modules = await reachedModulesOrFail(root, sources, directory, failures);
  if (modules === null) return;
  const found = rendererPackages(modules);
  console.log(directory, [...found.keys()].sort().join(" ") || "(no drawing library)");
  for (const { module } of found.values()) failures.push(`glass-shared reaches ${relative(root, module)}`);
}

await checkFrontEnd("apps/workspace", ["src/main.tsx"], { required: true });
// `pages`' drawing modules: one folder each under `apps/pages/modules`, each with an `index.ts`. Until the first
// exists there is nothing of `pages` that draws, and nothing to check.
const pagesModules = walk(join(root, "apps/pages/modules"), (path) => /\/index\.ts$/.test(path)).map((path) =>
  relative(join(root, "apps/pages"), path),
);
if (pagesModules.length) await checkFrontEnd("apps/pages", pagesModules, { required: true });
else console.log("apps/pages (no drawing module yet)");
await checkSharedPackage();

if (failures.length) {
  console.log(`FAIL\n${failures.join("\n")}`);
  process.exit(1);
}
console.log("PASS");
