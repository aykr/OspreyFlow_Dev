// ADR-152 invariant I1: no React in `apps/pages` or `packages/glass-shared`.
//
//   node scripts/no_react_check.mjs [root]        root defaults to the checkout this script is in
//
// Four things are checked, and the first failure in any of them fails the whole run (exit 1, "FAIL" and one line
// for each finding); a clean run says "PASS" and what it looked at, so a check that saw nothing cannot be mistaken
// for one that saw everything.
//
//   1. Resolved packages. Each tree's dependency closure, read from `package-lock.json` the way `npm ci` installs
//      it, holds no `react` or `react-dom`. Optional peers are not followed: `zustand` declares `react` as an
//      optional peer, so it is not installed for a tree that uses `zustand/vanilla`, and a tree is not blamed for
//      a package it does not get.
//   2. Source. No file of either tree names `react`, `react-dom`, `react/jsx-runtime` or any subpath of them in an
//      import, a re-export, a dynamic import, a `require` or a type; and none holds JSX, which compiles to
//      `react/jsx-runtime` whether or not the file imports React.
//   3. What the shared package reaches. Its source files, bundled as the build bundles them, reach no module of
//      `react`, `react-dom` or `scheduler`: this finds React arriving through another package (`import ... from
//      "zustand"` pulls `react` in; `zustand/vanilla` does not).
//   4. Bundles `pages` serves. No `.js`, `.mjs` or `.cjs` file under `apps/pages/dist` (or the shared package's)
//      carries a React marker: `react/jsx-runtime`, `react/jsx-dev-runtime`, `react-dom`, or the element symbol
//      (`Symbol.for("react.element")`, `Symbol.for("react.transitional.element")`).
//
// `OspreyFlow_Build/tests/glass_trees/test_no_react_check.py` plants each fault in the shape this check meets it.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { SOURCE, TEST_FILE, packageNameOf, reachedModulesOrFail, readImports, walk } from "./lib/glass_trees.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const root = resolve(process.argv[2] ?? join(HERE, ".."));

const TREES = [
  { name: "apps/pages", directory: "apps/pages" },
  { name: "packages/glass-shared", directory: "packages/glass-shared" },
];
const REACT_PACKAGES = new Set(["react", "react-dom"]);
const REACT_MODULE = /\/node_modules\/(react|react-dom|scheduler)\//;
const MARKERS = [
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "react-dom",
  "react.element",
  "react.transitional.element",
];

const failures = [];
const seen = { packages: 0, files: 0, modules: 0, bundles: 0 };

// 1. Resolved packages ---------------------------------------------------------------------------------------------
function locate(lock, from, name) {
  let base = from;
  for (;;) {
    const key = `${base ? `${base}/` : ""}node_modules/${name}`;
    if (lock.packages[key]) return key;
    if (!base) return null;
    const at = base.lastIndexOf("/node_modules/");
    base = at === -1 ? "" : base.slice(0, at);
  }
}

function dependenciesOf(entry, isTree) {
  const names = new Set();
  for (const kind of ["dependencies", "optionalDependencies"]) for (const name of Object.keys(entry[kind] ?? {})) names.add(name);
  if (isTree) for (const name of Object.keys(entry.devDependencies ?? {})) names.add(name);
  for (const name of Object.keys(entry.peerDependencies ?? {})) {
    if (!entry.peerDependenciesMeta?.[name]?.optional) names.add(name);
  }
  return [...names];
}

function checkResolvedPackages() {
  const lockPath = join(root, "package-lock.json");
  if (!existsSync(lockPath)) {
    failures.push("package-lock.json not found: the resolved packages cannot be read");
    return;
  }
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  for (const tree of TREES) {
    const top = lock.packages?.[tree.directory];
    if (!top) {
      failures.push(`${tree.name} is not in package-lock.json: run npm install to put it there`);
      continue;
    }
    const visited = new Set([tree.directory]);
    const queue = [[tree.directory, [tree.name]]];
    while (queue.length) {
      const [key, chain] = queue.shift();
      const entry = lock.packages[key];
      for (const name of dependenciesOf(entry, key === tree.directory)) {
        const found = locate(lock, key, name);
        if (found === null) continue; // not installed (an optional dependency for another platform)
        const target = lock.packages[found].link ? lock.packages[found].resolved : found;
        if (REACT_PACKAGES.has(name)) {
          failures.push(`${tree.name} resolves ${name}: ${[...chain, name].join(" > ")}`);
          continue;
        }
        if (visited.has(target) || !lock.packages[target]) continue;
        visited.add(target);
        queue.push([target, [...chain, name]]);
      }
    }
    seen.packages += visited.size;
  }
}

// 2 and 3. Source, and what the shared package reaches ---------------------------------------------------------------
function isReact(specifier) {
  return REACT_PACKAGES.has(packageNameOf(specifier));
}

async function checkSource() {
  for (const tree of TREES) {
    const directory = join(root, tree.directory);
    for (const file of walk(directory, (path) => SOURCE.test(path))) {
      seen.files += 1;
      const shown = relative(root, file);
      let found;
      try {
        found = readImports(file);
      } catch (error) {
        failures.push(`${shown} could not be read: ${error.message}`);
        continue;
      }
      for (const specifier of new Set(found.specifiers)) {
        if (isReact(specifier)) failures.push(`${shown} imports ${specifier}`);
      }
      if (found.jsx) failures.push(`${shown} holds JSX, which compiles to react/jsx-runtime`);
    }
  }
  const shared = join(root, "packages/glass-shared/src");
  const entries = walk(shared, (path) => /\.[cm]?[jt]sx?$/.test(path) && !TEST_FILE.test(path));
  if (entries.length) {
    const modules = await reachedModulesOrFail(root, entries, "packages/glass-shared", failures);
    seen.modules += modules?.size ?? 0;
    for (const id of modules ?? []) {
      if (REACT_MODULE.test(id)) failures.push(`packages/glass-shared reaches ${relative(root, id)}`);
    }
  }
}

// 4. Bundles `pages` serves ------------------------------------------------------------------------------------------
function checkBundles() {
  for (const directory of ["apps/pages/dist", "packages/glass-shared/dist"]) {
    for (const file of walk(join(root, directory), (path) => /\.(js|mjs|cjs)$/.test(path))) {
      seen.bundles += 1;
      const text = readFileSync(file, "utf8");
      for (const marker of MARKERS) {
        if (text.includes(marker)) failures.push(`${relative(root, file)} carries the React marker ${marker}`);
      }
    }
  }
}

checkResolvedPackages();
await checkSource();
checkBundles();

const looked = `${seen.packages} resolved packages, ${seen.files} source files, ${seen.modules} modules reached, ${seen.bundles} bundle files`;
if (failures.length) {
  console.log(`FAIL (${looked})`);
  for (const failure of failures) console.log(failure);
  process.exit(1);
}
console.log(`PASS (${looked})`);
