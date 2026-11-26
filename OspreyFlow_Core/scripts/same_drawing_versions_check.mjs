// ADR-152 invariant I20 (ADR-002 Amendment 1): both front ends resolve the same versions of `sigma`, `@sigma/*`,
// `maplibre-gl` and `graphology`, except a difference written in `apps/pages/VERSION_WINDOW.yaml` with the day it
// opened; and no release is cut while that file lists anything (slice WS4a).
//
//   node scripts/same_drawing_versions_check.mjs [root]             the merge check: exit 0 and "PASS", or 1 and "FAIL"
//   node scripts/same_drawing_versions_check.mjs [root] --release   the same, and refused while the window lists anything
//
// root defaults to the checkout this script is in. What it reads is the resolved tree, not the ranges: every entry of
// `package-lock.json`'s `packages`, from each front end (`apps/workspace`, `apps/pages`) outwards, by the rule Node and
// npm resolve a name with (the nearest `node_modules/<name>` from the requiring package's own folder upwards, a
// workspace link followed to its folder). So a copy npm nested under one package (`node_modules/x/node_modules/sigma`)
// counts for the front end that reaches it through `x`, exactly as the bundler would load it.
//
// Three kinds of finding, each a failure:
//   * one front end reaching two versions of one drawing library (a nested duplicate; a plugin bound to another copy
//     of the renderer than the page draws with). The window cannot excuse this: it lists differences between the two
//     front ends, not inside one;
//   * the two front ends reaching different versions of one library, with no entry in the window naming exactly that
//     package and those two versions with a valid day it opened; and an entry the tree no longer bears out (the
//     versions moved, or the difference closed), since a window that outlives its difference is no longer short;
//   * with --release, any entry at all.
// A lockfile, front end or window file that cannot be read is a failure: a check with nothing to compare must not pass.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const release = args.includes("--release");
const root = resolve(args.find((a) => !a.startsWith("--")) ?? join(HERE, ".."));

export const FRONT_ENDS = ["apps/workspace", "apps/pages"];
export const WINDOW_FILE = "apps/pages/VERSION_WINDOW.yaml";
const DRAWING = /^(sigma|@sigma\/[^/]+|maplibre-gl|graphology)$/;
const ENTRY_KEYS = ["package", "apps/workspace", "apps/pages", "opened"];

const failures = [];

/** The lockfile's own entry for the package `name` as `from` (a lockfile key) requires it, and that entry's key. */
function resolveName(packages, from, name) {
  let dir = from;
  // Every folder from the requirer's own up to the root. A folder that cannot hold a `node_modules` (`node_modules`
  // itself, a scope's `@x`) only yields a key the lockfile never has, so it needs no case of its own.
  for (;;) {
    const key = dir === "" ? `node_modules/${name}` : `${dir}/node_modules/${name}`;
    if (packages[key]) return followLink(packages, key);
    if (dir === "") return null;
    const up = posix.dirname(dir);
    dir = up === "." ? "" : up;
  }
}

function followLink(packages, key) {
  const entry = packages[key];
  if (entry?.link) {
    const target = entry.resolved;
    if (typeof target !== "string" || !packages[target]) return null;
    return { key: target, entry: packages[target] };
  }
  return { key, entry };
}

/** Every drawing library the front end at `start` reaches, as name -> Map(version -> the first lockfile key seen). */
function reached(packages, start) {
  const found = new Map();
  const seen = new Set();
  const queue = [start];
  while (queue.length) {
    const key = queue.shift();
    if (seen.has(key)) continue;
    seen.add(key);
    const entry = packages[key] ?? {};
    // A package's own folder, not one inside `node_modules`, is a workspace package: its devDependencies are built
    // with it (the pages service's bundle is made from them).
    const workspace = !key.split("/").includes("node_modules");
    const wanted = {
      ...(workspace ? entry.devDependencies : {}),
      ...entry.peerDependencies,
      ...entry.optionalDependencies,
      ...entry.dependencies,
    };
    for (const name of Object.keys(wanted)) {
      const hit = resolveName(packages, key, name);
      if (!hit) {
        const optional = name in (entry.optionalDependencies ?? {}) || name in (entry.peerDependencies ?? {});
        if (DRAWING.test(name) && !optional) failures.push(`${key || "the root"} needs ${name}, which the lockfile does not resolve`);
        continue;
      }
      if (DRAWING.test(name)) {
        const version = hit.entry.version;
        if (!found.has(name)) found.set(name, new Map());
        if (!found.get(name).has(version)) found.get(name).set(version, hit.key);
      }
      queue.push(hit.key);
    }
  }
  return found;
}

/** The window file, in the one shape it is written in; anything else is refused in words, never read as empty. */
export function readWindow(text) {
  const problems = [];
  const lines = text.split(/\r?\n/).map((l) => l.replace(/\s+#.*$/, "").replace(/^#.*$/, "")).filter((l) => l.trim() !== "");
  if (lines.length === 0 || !/^windows:\s*(\[\])?\s*$/.test(lines[0])) {
    return { entries: [], problems: ["it must begin `windows: []` (no difference open) or `windows:` followed by its entries"] };
  }
  const entries = [];
  if (/\[\]/.test(lines[0])) {
    if (lines.length > 1) problems.push("`windows: []` says it is empty, yet lines follow it");
    return { entries, problems };
  }
  let current = null;
  for (const line of lines.slice(1)) {
    const item = /^ {2}- ([^:]+):\s*(.*)$/.exec(line);
    const field = /^ {4}([^:]+):\s*(.*)$/.exec(line);
    const match = item ?? field;
    if (!match || (field && !current)) {
      problems.push(`a line it cannot read: ${JSON.stringify(line)}`);
      continue;
    }
    if (item) entries.push((current = {}));
    const [, key, raw] = match;
    const value = raw.trim().replace(/^"(.*)"$/, "$1").replace(/^'(.*)'$/, "$1");
    if (!ENTRY_KEYS.includes(key)) problems.push(`an entry has a field ${JSON.stringify(key)}; it takes ${ENTRY_KEYS.join(", ")}`);
    else if (key in current) problems.push(`an entry gives ${key} twice`);
    else current[key] = value;
  }
  if (entries.length === 0) problems.push("`windows:` with no entries: write `windows: []`");
  for (const entry of entries) {
    const name = entry.package ?? "(no package)";
    for (const key of ENTRY_KEYS) {
      if (!entry[key]) problems.push(`the entry for ${name} gives no ${key === "opened" ? "day it opened (opened: YYYY-MM-DD)" : key}`);
    }
    if (entry.package && !DRAWING.test(entry.package)) problems.push(`the entry for ${name} is not a drawing library I20 holds equal`);
    if (entry.opened && !isDay(entry.opened)) problems.push(`the entry for ${name} opened on ${JSON.stringify(entry.opened)}, which is not a day (YYYY-MM-DD)`);
  }
  return { entries, problems };
}

function isDay(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return false;
  const day = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return day.toISOString().slice(0, 10) === text;
}

function main() {
  const lockPath = join(root, "package-lock.json");
  if (!existsSync(lockPath)) {
    failures.push(`no package-lock.json at ${root}: nothing resolved to compare`);
    return;
  }
  const packages = JSON.parse(readFileSync(lockPath, "utf8")).packages;
  if (!packages || typeof packages !== "object") {
    failures.push("package-lock.json has no `packages` (lockfile version 2 or later is needed)");
    return;
  }
  const trees = {};
  for (const front of FRONT_ENDS) {
    if (!packages[front]) failures.push(`the lockfile has no front end ${front}: nothing to compare`);
    else trees[front] = reached(packages, front);
  }
  const windowPath = join(root, WINDOW_FILE);
  let window = { entries: [], problems: [] };
  if (!existsSync(windowPath)) failures.push(`no ${WINDOW_FILE}: the window file is kept even when empty (\`windows: []\`)`);
  else window = readWindow(readFileSync(windowPath, "utf8"));
  for (const problem of window.problems) failures.push(`${WINDOW_FILE}: ${problem}`);
  if (failures.length) return;

  // Inside one front end: one version of each.
  const single = {};
  for (const front of FRONT_ENDS) {
    single[front] = new Map();
    for (const [name, versions] of trees[front]) {
      if (versions.size > 1) {
        const where = [...versions].map(([v, key]) => `${v} (${key})`).join(" and ");
        failures.push(`${front} reaches two versions of ${name}: ${where}`);
      } else single[front].set(name, [...versions.keys()][0]);
    }
  }
  // Between the two: the same, or written in the window.
  const [a, b] = FRONT_ENDS;
  const listed = new Map(window.entries.map((e) => [e.package, e]));
  const differing = new Set();
  for (const [name, va] of single[a]) {
    const vb = single[b].get(name);
    if (vb === undefined || vb === va) continue;
    differing.add(name);
    const entry = listed.get(name);
    if (!entry) failures.push(`${name}: ${a} resolves ${va} and ${b} resolves ${vb}, and ${WINDOW_FILE} does not list it`);
    else if (entry[a] !== va || entry[b] !== vb) {
      failures.push(`${name}: ${a} resolves ${va} and ${b} resolves ${vb}, but ${WINDOW_FILE} lists ${entry[a]} and ${entry[b]}`);
    }
  }
  for (const entry of window.entries) {
    if (!differing.has(entry.package)) {
      failures.push(`${WINDOW_FILE} lists ${entry.package} (opened ${entry.opened}), but the two front ends do not differ in it: take the entry out`);
    }
  }
  if (release && window.entries.length) {
    const open = window.entries.map((e) => `${e.package} (${e[a]} in ${a}, ${e[b]} in ${b}, opened ${e.opened})`).join("; ");
    failures.push(`no release while ${WINDOW_FILE} lists anything (ADR-002 Amendment 1, item 3): ${open}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
  if (failures.length) {
    console.log(`FAIL same drawing versions (I20)${release ? ", release" : ""}`);
    for (const f of failures) console.log(`  ${f}`);
    process.exit(1);
  }
  console.log(`PASS same drawing versions (I20)${release ? ", release" : ""}: ${FRONT_ENDS.join(" and ")} resolve one version of each drawing library they share`);
}
