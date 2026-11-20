// Compares two builds of `apps/workspace`: the same behaviour under another path is the same build; a different
// behaviour is not (ADR-152 invariant I11, the owner's condition (a) of 20 November 2026; slice PL4a).
//
//   node scripts/dist_compare.mjs compare <before-dist> <after-dist>
//        exit 0 and "SAME" when the two builds differ only as a file's new path makes them differ; exit 1 and
//        "DIFFERENT" with what changed otherwise.
//   node scripts/dist_compare.mjs normalise <dist>
//        the normalised hash of one build, and what it was made from.
//   node scripts/dist_compare.mjs record --dist <dist> --tests <npm-test-output> [--out <file>]
//        writes the baseline record (default `apps/workspace/PL4_BASELINE.json`): the normalised hash, the file
//        counts and the unit-test counts of `npm test --workspace apps/workspace`.
//   node scripts/dist_compare.mjs verify [--build] [--dist <dist>] [--record <file>] [--tests <npm-test-output>]
//        builds `apps/workspace` (with --build), then compares its normalised hash with the record's.
//
// What is tolerated, because only a file's new path can cause it (each case is planted in
// `OspreyFlow_Build/tests/glass_trees/test_dist_compare.py`, and was shown against real `vite build` output):
//   * file names that carry a content hash (`assets/<name>-<hash>.<ext>`): a chunk or asset is identified by what
//     it holds, never by its name or its hash, and a reference from one file to another is read as the content of
//     the file it names (iterated, so a cycle of chunks settles);
//   * source maps, and the comment that points to one;
//   * the order of a JavaScript chunk's top-level statements and of its `var a = …, b = …` declarators (module
//     order), and of the statements of a chunk that is one wrapping function (a bundled worker);
//   * the names of bindings: a minifier names them by how often they are used, so they move when code does.
//     Within one statement the bindings are compared as a pattern (the first binding named is `$0`, the next `$1`;
//     eslint-scope says which name is which binding, so a parameter spelled like an outer variable is another one),
//     so `f(a, b)` is not `f(a, a)`; a global (`Object`, `document`), a property (`x.length`) and a key keep their names.
//   * whitespace and comments in CSS.
// What fails: a string, a number, an operator, a condition, a property name, a call's shape, a statement or
// declarator added or removed, an import or export added or removed, a different CSS rule, a CSS rule moved (the
// cascade reads in order), a file added, removed or changed that has no hash in its name (a file a page asks for by
// name), and any asset whose bytes differ.
//
// What it cannot see, said here so nobody takes it for more: which of two same-shaped names a statement refers to
// (`f(a)` that becomes `f(b)`, with `a` and `b` different bindings), since names are not compared. The unit tests
// and the browser gates are what stand behind that.
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE = resolve(HERE, "..");
const requireCore = createRequire(join(CORE, "package.json"));
const { parseSync } = requireCore("rolldown/utils");
const eslintScope = requireCore("eslint-scope");

/** Changed whenever the way a build is normalised changes: a record made under another version is not comparable. */
export const NORMALISER_VERSION = 1;

const REF = "\u0001";
const sha = (text) => createHash("sha256").update(text).digest("hex");

// ---------------------------------------------------------------------------------------------------- reading a build

function walkFiles(directory) {
  const found = [];
  for (const name of readdirSync(directory).sort()) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) found.push(...walkFiles(path));
    else found.push(path);
  }
  return found;
}

// `assets/<stem>-<hash>.<ext>`, directly under `assets/`: what Vite names an output whose name carries a content hash.
// A file under `assets/govuk/` is copied from `public/` and keeps its name, which a page asks for.
const HASHED = /^assets\/([^/]+)-([A-Za-z0-9_-]{8})(\.[A-Za-z0-9.]+)$/;

function classify(rel) {
  const match = HASHED.exec(rel);
  if (match) return { hashed: true, stem: match[1], ext: match[3] };
  const dot = rel.lastIndexOf(".");
  return { hashed: false, stem: rel, ext: dot === -1 ? "" : rel.slice(dot) };
}

const SKIPPED = (rel) => rel.endsWith(".map") || rel.endsWith(".DS_Store");

// -------------------------------------------------------------------------------------------- canonical JavaScript

function visit(node, parent, key, callback) {
  if (Array.isArray(node)) {
    for (const child of node) visit(child, parent, key, callback);
  } else if (node && typeof node === "object") {
    if (typeof node.type === "string") callback(node, parent, key);
    for (const field of Object.keys(node)) {
      if (field !== "loc" && field !== "range" && field !== "start" && field !== "end") visit(node[field], node.type ? node : parent, field, callback);
    }
  }
}

/**
 * Every identifier of the program that names a binding the program declares (a declaration or a reference to one),
 * with the binding it names. A name no declaration in the program owns is a global (`Object`, `document`) and is not
 * here. Read with eslint-scope, so a parameter that happens to be spelled like the variable outside it is another
 * binding: a minifier reuses short names freely, and a pattern of names that ignored scope would see a difference
 * where a move made none.
 */
function bindingsOf(program, sourceType) {
  const manager = eslintScope.analyze(program, { ecmaVersion: 2024, sourceType, fallback: "iteration" });
  const occurrence = new Map();
  for (const scope of manager.scopes) {
    for (const variable of scope.variables) {
      if (variable.defs.length === 0) continue; // `arguments`, and the like: no declaration, no name of the build's own
      for (const identifier of variable.identifiers) occurrence.set(identifier, variable);
      for (const reference of variable.references) occurrence.set(reference.identifier, variable);
    }
  }
  const shorthand = new Map(); // `{ a }`: the value names `a`, and so does the key, which is a property name and stays
  visit(program, null, null, (node) => {
    if (node.type !== "Property" || !node.shorthand || node.computed) return;
    const value = node.value?.type === "AssignmentPattern" ? node.value.left : node.value;
    if (value?.type === "Identifier") shorthand.set(value, node.key.name ?? node.key.value);
  });
  return { occurrence, shorthand };
}

/** The text of `node` from `text`, each binding replaced by `$n`, numbered in the order the unit first names them. */
function patterned(text, node, bindings) {
  const found = [];
  visit(node, null, null, (child) => {
    if (child.type === "Identifier" && bindings.occurrence.has(child)) found.push(child);
  });
  found.sort((a, b) => a.start - b.start);
  const numbers = new Map();
  let out = "";
  let at = node.start;
  for (const identifier of found) {
    if (identifier.start < at) continue;
    const variable = bindings.occurrence.get(identifier);
    if (!numbers.has(variable)) numbers.set(variable, numbers.size);
    const key = bindings.shorthand.get(identifier);
    out += `${text.slice(at, identifier.start)}${key === undefined ? "" : `${key}:`}$${numbers.get(variable)}`;
    at = identifier.end;
  }
  return out + text.slice(at, node.end);
}

function unwrap(node) {
  let current = node;
  while (current && (current.type === "ParenthesizedExpression" || current.type === "ChainExpression")) current = current.expression;
  return current;
}

// `(function(){ … })()` and `(()=>{ … })()`: a chunk that is one function (a bundled worker) is compared by what is inside it.
function iifeBody(statement) {
  if (statement.type !== "ExpressionStatement") return null;
  let expression = unwrap(statement.expression);
  if (expression?.type === "UnaryExpression" && expression.operator === "!") expression = unwrap(expression.argument);
  if (expression?.type !== "CallExpression") return null;
  const callee = unwrap(expression.callee);
  if (!callee || (callee.type !== "FunctionExpression" && callee.type !== "ArrowFunctionExpression")) return null;
  if (callee.body?.type !== "BlockStatement" || expression.arguments.length > 0 || callee.params.length > 0) return null;
  return callee.body.body;
}

function importExportShape(text, statement) {
  const source = statement.source ? `from${text.slice(statement.source.start, statement.source.end)}` : "";
  const count = statement.specifiers?.length ?? 0;
  const kind = statement.type === "ImportDeclaration" ? "import" : "export";
  if (statement.type === "ExportAllDeclaration") return `export*${statement.exported ? "as" : ""}${source}`;
  return `${kind}{*${count}}${source}`;
}

/** The comparable units of a chunk: one string for each top-level statement and each declarator, order forgotten. */
function jsUnits(path, text) {
  const body = text; // comments (the source map's among them) are not statements, so the parser leaves them out
  let sourceType = "module";
  let result = parseSync(path, body, { lang: "js", sourceType, preserveParens: false, range: true });
  if (result.errors.length) {
    sourceType = "script";
    result = parseSync(path, body, { lang: "js", sourceType, preserveParens: false, range: true });
  }
  if (result.errors.length) return { units: [`unparsed:${sha(body)}`], parsed: false };
  const bindings = bindingsOf(result.program, sourceType);
  const units = [];
  const emit = (statements) => {
    for (const statement of statements) {
      const inner = iifeBody(statement);
      if (inner) {
        units.push("iife");
        emit(inner);
      } else if (statement.type === "VariableDeclaration") {
        for (const declarator of statement.declarations) units.push(`${statement.kind} ${patterned(body, declarator, bindings)}`);
      } else if (statement.type === "ImportDeclaration" || statement.type === "ExportAllDeclaration" || (statement.type === "ExportNamedDeclaration" && !statement.declaration)) {
        units.push(importExportShape(body, statement));
      } else if (statement.type === "EmptyStatement" || statement.type === "Directive") {
        // nothing to compare
      } else {
        units.push(patterned(body, statement, bindings));
      }
    }
  };
  emit(result.program.body);
  return { units, parsed: true };
}

// ---------------------------------------------------------------------------------------------- canonical CSS and HTML

/** CSS rules at the top level, in order: comments gone, whitespace collapsed. A rule moved is a change (the cascade reads in order). */
function cssUnits(text) {
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ").replace(/\s*([{};,])\s*/g, "$1").trim();
  const rules = [];
  let depth = 0;
  let start = 0;
  for (let at = 0; at < clean.length; at += 1) {
    const char = clean[at];
    if (char === "{") depth += 1;
    else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        rules.push(clean.slice(start, at + 1));
        start = at + 1;
      }
    } else if (char === ";" && depth === 0) {
      rules.push(clean.slice(start, at + 1));
      start = at + 1;
    }
  }
  if (start < clean.length) rules.push(clean.slice(start));
  return rules.map((rule, index) => `${index}:${rule}`);
}

// ----------------------------------------------------------------------------------------------------- the build

/**
 * Reads a build folder into comparable files. Each file's `units` hold `\u0001<name>\u0001` wherever the file names
 * another hashed file, so the reference can be read as that file's content later.
 */
export function readBuild(dist) {
  const root = resolve(dist);
  if (!existsSync(root) || !statSync(root).isDirectory()) throw new Error(`not a build folder: ${dist}`);
  const entries = walkFiles(root)
    .map((path) => ({ path, rel: relative(root, path).split("\\").join("/") }))
    .filter(({ rel }) => !SKIPPED(rel));
  const hashedNames = entries.filter(({ rel }) => HASHED.test(rel)).map(({ rel }) => rel.slice(rel.lastIndexOf("/") + 1));
  const mention = hashedNames.length
    ? new RegExp(hashedNames.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g")
    : null;
  const mark = (text) => (mention ? text.replace(mention, (name) => `${REF}${name}${REF}`) : text);

  const files = entries.map(({ path, rel }) => {
    const bytes = readFileSync(path);
    const { hashed, stem, ext } = classify(rel);
    const file = { rel, hashed, stem, ext, size: bytes.length, name: rel.slice(rel.lastIndexOf("/") + 1) };
    if (ext === ".js" || ext === ".mjs") {
      const { units, parsed } = jsUnits(rel, bytes.toString("utf8"));
      file.kind = "js";
      file.units = units.map(mark);
      file.ordered = false;
      file.parsed = parsed;
    } else if (ext === ".css") {
      file.kind = "css";
      file.units = cssUnits(bytes.toString("utf8")).map(mark);
      file.ordered = true;
    } else if (ext === ".html") {
      file.kind = "html";
      file.units = bytes.toString("utf8").split("\n").map(mark);
      file.ordered = true;
    } else {
      file.kind = "bytes";
      file.units = [createHash("sha256").update(bytes).digest("hex")];
      file.ordered = true;
    }
    return file;
  });
  return files;
}

/** A label for every file, from what it holds and (iterated three times) from the labels of the files it names. */
function label(files) {
  const byName = new Map(files.filter((file) => file.hashed).map((file) => [file.name, file]));
  let labels = new Map(files.map((file) => [file.rel, "0"]));
  for (let round = 0; round < 3; round += 1) {
    const next = new Map();
    const resolveUnit = (unit) =>
      unit.includes(REF)
        ? unit.replace(new RegExp(`${REF}([^${REF}]+)${REF}`, "g"), (_, name) => `<${byName.has(name) ? labels.get(byName.get(name).rel) : "unknown"}>`)
        : unit;
    for (const file of files) {
      file.resolved = file.units.map(resolveUnit);
      file.base = file.units.map((unit) => unit.replace(new RegExp(`${REF}[^${REF}]+${REF}`, "g"), "<file>"));
      const hashes = file.resolved.map(sha);
      if (!file.ordered) hashes.sort();
      next.set(file.rel, sha(`${file.kind}\n${hashes.join("\n")}`));
    }
    labels = next;
  }
  for (const file of files) file.label = labels.get(file.rel);
  return files;
}

/** The normalised form of a build: every file with its label, and one hash over all of them. */
export function normalise(dist) {
  const files = label(readBuild(dist));
  const keys = files.map((file) => (file.hashed ? `chunk${file.ext}:${file.label}` : `file:${file.rel}:${file.label}`)).sort();
  return { hash: sha(keys.join("\n")), files };
}

// ----------------------------------------------------------------------------------------------------- comparing

function readable(unit) {
  return unit.length > 220 ? `${unit.slice(0, 217)}...` : unit;
}

function multiset(items) {
  const counts = new Map();
  for (const item of items) counts.set(item, (counts.get(item) ?? 0) + 1);
  return counts;
}

function unitDifference(before, after, ordered) {
  if (ordered) {
    const b = before.base;
    const a = after.base;
    const first = [...Array(Math.max(b.length, a.length)).keys()].find((index) => b[index] !== a[index]);
    return {
      removed: first === undefined ? [] : [b[first]].filter((unit) => unit !== undefined),
      added: first === undefined ? [] : [a[first]].filter((unit) => unit !== undefined),
      note: first === undefined ? "" : `first difference at unit ${first + 1} of ${b.length} before, ${a.length} after`,
    };
  }
  const left = multiset(before.base);
  const right = multiset(after.base);
  const removed = [];
  const added = [];
  for (const [unit, count] of left) for (let i = right.get(unit) ?? 0; i < count; i += 1) removed.push(unit);
  for (const [unit, count] of right) for (let i = left.get(unit) ?? 0; i < count; i += 1) added.push(unit);
  return { removed, added, note: "" };
}

function commonUnits(before, after) {
  const right = new Set(after.base);
  return before.base.filter((unit) => right.has(unit)).length;
}

/** Everything that differs between two builds, in words. An empty list is "the same build". */
export function compareBuilds(beforeDist, afterDist) {
  const before = normalise(beforeDist);
  const after = normalise(afterDist);
  const findings = [];
  const fixedBefore = new Map(before.files.filter((f) => !f.hashed).map((f) => [f.rel, f]));
  const fixedAfter = new Map(after.files.filter((f) => !f.hashed).map((f) => [f.rel, f]));
  for (const [rel, file] of fixedBefore) {
    const other = fixedAfter.get(rel);
    if (!other) findings.push({ title: `removed: ${rel} (a file a page asks for by name)`, lines: [] });
    else if (other.label !== file.label) findings.push(describeChange(`changed: ${rel}`, file, other));
  }
  for (const rel of fixedAfter.keys()) if (!fixedBefore.has(rel)) findings.push({ title: `added: ${rel} (a file a page asks for by name)`, lines: [] });

  // Files named by a content hash are matched by what they hold, never by name.
  const poolBefore = before.files.filter((f) => f.hashed);
  const poolAfter = after.files.filter((f) => f.hashed);
  const key = (f) => `${f.ext}:${f.label}`;
  const afterCounts = multiset(poolAfter.map(key));
  const unmatchedBefore = [];
  for (const file of poolBefore) {
    const left = afterCounts.get(key(file)) ?? 0;
    if (left > 0) afterCounts.set(key(file), left - 1);
    else unmatchedBefore.push(file);
  }
  const beforeCounts = multiset(poolBefore.map(key));
  const unmatchedAfter = [];
  for (const file of poolAfter) {
    const left = beforeCounts.get(key(file)) ?? 0;
    if (left > 0) beforeCounts.set(key(file), left - 1);
    else unmatchedAfter.push(file);
  }
  for (const file of unmatchedBefore) {
    const candidates = unmatchedAfter.filter((other) => other.kind === file.kind && other.ext === file.ext);
    let best = null;
    let bestShared = -1;
    for (const other of candidates) {
      const shared = file.kind === "bytes" ? 0 : commonUnits(file, other);
      if (shared > bestShared) [best, bestShared] = [other, shared];
    }
    if (best && file.kind !== "bytes") {
      unmatchedAfter.splice(unmatchedAfter.indexOf(best), 1);
      findings.push(describeChange(`changed: ${file.stem}${file.ext} (named ${file.name} before, ${best.name} after)`, file, best));
    } else if (best && file.stem === best.stem) {
      unmatchedAfter.splice(unmatchedAfter.indexOf(best), 1);
      findings.push({ title: `changed: ${file.stem}${file.ext}: the bytes differ (${file.size} before, ${best.size} after)`, lines: [] });
    } else {
      findings.push({ title: `removed: ${file.stem}${file.ext} (${file.name}, ${file.size} bytes)`, lines: [] });
    }
  }
  for (const file of unmatchedAfter) findings.push({ title: `added: ${file.stem}${file.ext} (${file.name}, ${file.size} bytes)`, lines: [] });

  findings.sort((a, b) => Number(Boolean(a.knockOn)) - Number(Boolean(b.knockOn)));
  if (findings.length === 0 && before.hash !== after.hash) {
    findings.push({ title: "the normalised hashes differ though no single file does (a cycle of chunks, or a reference to another file)", lines: [] });
  }
  return { before, after, findings };
}

function describeChange(title, before, after) {
  const { removed, added, note } = unitDifference(before, after, before.ordered);
  if (removed.length === 0 && added.length === 0 && !note) {
    // Nothing in this file changed: it names a file that did, or names another file than it did.
    return { title: `${title.replace(/^changed:/, "also differs:")} (it names a file that changed, or names another file)`, lines: [], knockOn: true };
  }
  const lines = [];
  if (note) lines.push(`  ${note}`);
  for (const unit of removed.slice(0, 5)) lines.push(`  - ${readable(unit)}`);
  if (removed.length > 5) lines.push(`  - ... and ${removed.length - 5} more only before`);
  for (const unit of added.slice(0, 5)) lines.push(`  + ${readable(unit)}`);
  if (added.length > 5) lines.push(`  + ... and ${added.length - 5} more only after`);
  return { title, lines };
}

// ---------------------------------------------------------------------------------------------------- the record

const ANSI = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, "g");

/** The counts in `npm test --workspace apps/workspace`'s output: it runs vitest twice, the main run and the budget run. */
export function parseTestCounts(output) {
  const text = output.replace(ANSI, "");
  const counts = (line) => {
    const result = { total: 0, passed: 0, failed: 0, skipped: 0 };
    for (const [, n, word] of line.matchAll(/(\d+) (failed|passed|skipped|todo)/g)) {
      if (word === "todo") continue;
      result[word] += Number(n);
    }
    const total = /\((\d+)\)/.exec(line);
    result.total = total ? Number(total[1]) : result.passed + result.failed + result.skipped;
    return result;
  };
  const filesLines = [...text.matchAll(/^\s*Test Files\s+(.*)$/gm)].map((m) => counts(m[1]));
  const testLines = [...text.matchAll(/^\s*Tests\s+(.*)$/gm)].map((m) => counts(m[1]));
  if (filesLines.length === 0 || filesLines.length !== testLines.length) throw new Error("no vitest summary (Test Files / Tests lines) in the test output");
  const names = ["main", "budget"];
  return filesLines.map((files, index) => ({ run: names[index] ?? `run-${index + 1}`, files, tests: testLines[index] }));
}

function fileCounts(files) {
  const byKind = {};
  for (const file of files) byKind[file.kind] = (byKind[file.kind] ?? 0) + 1;
  return { total: files.length, hashed: files.filter((f) => f.hashed).length, by_kind: Object.fromEntries(Object.entries(byKind).sort()) };
}

export function makeRecord(dist, testOutput) {
  const { hash, files } = normalise(dist);
  return {
    what: "The build of apps/workspace before PL4 moved anything (ADR-152 R2, I11): what every later PL4 slice is compared against.",
    normaliser_version: NORMALISER_VERSION,
    normalised_hash: hash,
    files: fileCounts(files),
    unit_tests: parseTestCounts(testOutput),
    not_recorded: "Performance budget figures: they are measured on the owner's Mac with nothing else running (slice E).",
  };
}

// -------------------------------------------------------------------------------------------------------- the CLI

function flag(args, name) {
  const at = args.indexOf(name);
  return at === -1 ? null : (args[at + 1] ?? null);
}

function runBuild() {
  const done = spawnSync("npm", ["run", "build", "--workspace", "apps/workspace"], { cwd: CORE, stdio: "inherit" });
  if (done.status !== 0) throw new Error("npm run build --workspace apps/workspace failed");
}

function printFindings(findings) {
  for (const finding of findings) {
    console.log(finding.title);
    for (const line of finding.lines) console.log(line);
  }
}

function main(args) {
  const [command, ...rest] = args;
  const recordPath = flag(rest, "--record") ?? join(CORE, "apps/workspace/PL4_BASELINE.json");
  switch (command) {
    case "compare": {
      const [before, after] = rest;
      if (!before || !after) throw new Error("usage: compare <before-dist> <after-dist>");
      const { before: a, after: b, findings } = compareBuilds(before, after);
      if (findings.length === 0) {
        console.log(`SAME (${a.files.length} files before, ${b.files.length} after; normalised hash ${a.hash.slice(0, 16)})`);
        return 0;
      }
      console.log(`DIFFERENT (${findings.length} finding${findings.length === 1 ? "" : "s"})`);
      printFindings(findings);
      return 1;
    }
    case "normalise": {
      const { hash, files } = normalise(rest[0]);
      console.log(JSON.stringify({ normalised_hash: hash, normaliser_version: NORMALISER_VERSION, files: fileCounts(files) }, null, 2));
      return 0;
    }
    case "record": {
      const dist = flag(rest, "--dist");
      const tests = flag(rest, "--tests");
      if (!dist || !tests) throw new Error("usage: record --dist <dist> --tests <npm-test-output> [--out <file>]");
      const out = flag(rest, "--out") ?? recordPath;
      const record = makeRecord(dist, readFileSync(tests, "utf8"));
      mkdirSync(dirname(out), { recursive: true });
      writeFileSync(out, `${JSON.stringify(record, null, 2)}\n`);
      console.log(`wrote ${relative(process.cwd(), out)}: ${record.files.total} files, hash ${record.normalised_hash.slice(0, 16)}`);
      return 0;
    }
    case "verify": {
      if (rest.includes("--build")) runBuild();
      const dist = flag(rest, "--dist") ?? join(CORE, "apps/workspace/dist");
      const record = JSON.parse(readFileSync(recordPath, "utf8"));
      if (record.normaliser_version !== NORMALISER_VERSION) {
        console.log(`DIFFERENT: the record was made by normaliser ${record.normaliser_version}, this is ${NORMALISER_VERSION}: compare the raw baseline copy with \`compare\` instead`);
        return 1;
      }
      const { hash, files } = normalise(dist);
      let failed = false;
      if (hash !== record.normalised_hash) {
        console.log(`DIFFERENT: the normalised hash is ${hash.slice(0, 16)}, the baseline's is ${record.normalised_hash.slice(0, 16)}`);
        console.log("Run `compare <raw baseline dist> <this dist>` for what changed.");
        failed = true;
      } else {
        console.log(`SAME as the baseline (${files.length} files; normalised hash ${hash.slice(0, 16)})`);
      }
      const testsPath = flag(rest, "--tests");
      if (testsPath) {
        const now = parseTestCounts(readFileSync(testsPath, "utf8"));
        for (const [index, run] of record.unit_tests.entries()) {
          const current = now[index];
          if (!current) continue;
          console.log(`${run.run}: ${current.tests.passed}/${current.tests.total} tests passed in ${current.files.total} files (baseline ${run.tests.passed}/${run.tests.total} in ${run.files.total})`);
        }
        if (now.some((run) => run.tests.failed > 0 || run.files.failed > 0)) {
          console.log("DIFFERENT: a test fails");
          failed = true;
        }
      }
      return failed ? 1 : 0;
    }
    default:
      throw new Error("usage: dist_compare.mjs compare|normalise|record|verify ...");
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    console.log(`ERROR: ${error.message}`);
    process.exitCode = 2;
  }
}
