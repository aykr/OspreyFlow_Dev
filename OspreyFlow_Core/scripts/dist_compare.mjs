// Compares two builds of `apps/workspace`: the same behaviour under another path is the same build; a different
// behaviour is not (ADR-152 invariant I11, the owner's condition (a) of 20 November 2026; slice PL4a).
//
//   node scripts/dist_compare.mjs compare <before-dist> <after-dist>
//        exit 0 and "SAME" when the two builds differ only as a file's new path makes them differ; exit 1 and
//        "DIFFERENT" with what changed otherwise.
//   node scripts/dist_compare.mjs units <before-dist> <after-dist>
//        every differing unit, uncapped, one per line: `<file>\t<only before|only after>\t<sha-12 of the unit>\t<unit>`
//        (a slice that splits code declares exactly these; `compare` shows five a side, this shows them all).
//   node scripts/dist_compare.mjs rebaseline --declared <file> [--baseline <folder>] [--dist <built>] [--tests <npm-test-output>] [--out <file>] [--conductor-merge]
//        REFUSES, in words and touching nothing, to run against the real baseline folder (a fixed path) or $PL4_BASELINE_DIST unless `--conductor-merge`
//        is given: only the conductor's merge passes it; everything else names a copy with `--baseline`.
//        the conductor's step at merge (PL4d3d, the owner's ruling of 21 November 2026), run from the merged commit:
//        builds the workspace from the checked-out tree (or takes `--dist`), compares it with the baseline folder (default
//        `$PL4_BASELINE_DIST`, else `~/dev/osprey-acceptance/PL4a-baseline/dist`), prints the old-against-new listing of
//        differing units and EXITS NON-ZERO, touching nothing, if any differing unit is not in the declared file
//        (`--declared`, required: the list of units a slice declares, a knock-on one included; this script lives in Core,
//        which does not name where that list is kept) or if a declared unit does not differ.
//        Otherwise it runs the workspace's unit tests, moves the old baseline folder aside (never deleted: a dated
//        sibling, `<name>-before-<date>`), puts the new build in its place and writes `PL4_BASELINE.json`.
//   node scripts/dist_compare.mjs normalise <dist>
//        the normalised hash of one build, and what it was made from.
//   node scripts/dist_compare.mjs record --dist <dist> --tests <npm-test-output> [--out <file>]
//        writes the baseline record (default `apps/workspace/PL4_BASELINE.json`): the normalised hash, the file
//        counts and the unit-test counts of `npm test --workspace apps/workspace`.
//   node scripts/dist_compare.mjs verify [--build] [--dist <dist>] [--record <file>] [--tests <npm-test-output>]
//        builds `apps/workspace` (with --build), then compares its normalised hash with the record's.
//
// What is tolerated, because only a file's new path can cause it (each case is planted in
// the developer repository's `tests/glass_trees/test_dist_compare.py`, and was shown against real `vite build` output):
//   * file names that carry a content hash (`assets/<name>-<hash>.<ext>`): a chunk or asset is identified by what
//     it holds, never by its name or its hash, and a reference from one file to another is read as the content of
//     the file it names (iterated, so a cycle of chunks settles);
//   * source maps, and the comment that points to one;
//   * the order of a JavaScript chunk's top-level statements and of its `var a = …, b = …` declarators (module
//     order), and of the statements of a chunk that is one wrapping function (a bundled worker);
//   * the names of bindings: a minifier names them by how often they are used, so they move when code does.
//     eslint-scope says which name is which binding, so a parameter spelled like an outer variable is another one.
//     A binding inside a statement (a parameter, an inner variable) is written by the order the statement first names
//     it (`$0`, `$1`), so `f(a, b)` is not `f(a, a)`. A binding the chunk declares at its top level is written by what it
//     is: the label of what its declaration holds, how it is used and (for an import) what the other chunk exports under
//     the name it imports, refined round by round until nothing splits further (as colours are refined on a graph).
//     So `f(a)` that becomes `f(b)` is a different build, and so is `import{x as f}` that becomes `import{y as f}`,
//     unless `a` and `b` are the same thing under two names. A global (`Object`, `document`), a property (`x.length`)
//     and a key keep their names.
//   * whitespace and comments in CSS.
// What fails: a string, a number, an operator, a condition, a property name, a call's shape, a reference or an import
// pointed at another binding, a statement or declarator added or removed, an export added or removed, a different CSS
// rule, a CSS rule moved (the cascade reads in order), a file added, removed or changed that has no hash in its name
// (a file a page asks for by name), and any asset whose bytes differ.
//
// What it cannot see, said here so nobody takes it for more: two top-level bindings that no round can tell apart
// (the same declaration and the same use at every depth) are one and the same to it, which they are, up to their names;
// and a difference more than SETTLED_ROUNDS references away from the text that carries it, once every label is told apart,
// may not reach it. The unit tests and the browser gates stand behind the rest.
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE = resolve(HERE, "..");
const requireCore = createRequire(join(CORE, "package.json"));
const { parseSync } = requireCore("rolldown/utils");
const eslintScope = requireCore("eslint-scope");

/** Changed whenever the way a build is normalised changes: a record made under another version is not comparable. */
export const NORMALISER_VERSION = 2;

const REF = "\u0001"; // around the name of a hashed file, where a file's text names it
const MARK = "\u0002"; // around the number of a top-level binding, where a unit's text names it
const MARK_PATTERN = new RegExp(`${MARK}(\\d+)${MARK}`, "g");
const REF_PATTERN = new RegExp(`${REF}([^${REF}]+)${REF}`, "g");
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
  return { occurrence, shorthand, manager };
}

/**
 * The text of `node` from `text` with every binding named in it written without its name. A binding the program
 * declares at the top level (of the chunk, or of the one wrapping function of a bundled worker) is written as a
 * marker that holds its number in the file: `label()` later reads it as what the binding holds and how it is used, so
 * a reference pointed at another binding changes the text. A binding that lives inside the unit (a parameter, an
 * inner variable) is written `$n`, numbered in the order the unit first names it.
 */
function patterned(text, node, bindings, table) {
  const found = [];
  visit(node, null, null, (child) => {
    if (child.type === "Identifier" && bindings.occurrence.has(child)) found.push(child);
  });
  found.sort((a, b) => a.start - b.start);
  const locals = new Map();
  const refs = [];
  let out = "";
  let at = node.start;
  for (const identifier of found) {
    if (identifier.start < at) continue;
    const variable = bindings.occurrence.get(identifier);
    let written;
    if (table.topLevel(variable)) {
      const id = table.idOf(variable);
      refs.push({ id, declares: variable.identifiers.includes(identifier) });
      written = `${MARK}${id}${MARK}`;
    } else {
      if (!locals.has(variable)) locals.set(variable, locals.size);
      written = `$${locals.get(variable)}`;
    }
    const key = bindings.shorthand.get(identifier);
    out += `${text.slice(at, identifier.start)}${key === undefined ? "" : `${key}:`}${written}`;
    at = identifier.end;
  }
  return { text: out + text.slice(at, node.end), refs };
}

function unwrap(node) {
  let current = node;
  while (current && (current.type === "ParenthesizedExpression" || current.type === "ChainExpression")) current = current.expression;
  return current;
}

// `(function(){ … })()` and `(()=>{ … })()`: a chunk that is one function (a bundled worker) is compared by what is inside it.
function iifeOf(statement) {
  if (statement.type !== "ExpressionStatement") return null;
  let expression = unwrap(statement.expression);
  if (expression?.type === "UnaryExpression" && expression.operator === "!") expression = unwrap(expression.argument);
  if (expression?.type !== "CallExpression") return null;
  const callee = unwrap(expression.callee);
  if (!callee || (callee.type !== "FunctionExpression" && callee.type !== "ArrowFunctionExpression")) return null;
  if (callee.body?.type !== "BlockStatement" || expression.arguments.length > 0 || callee.params.length > 0) return null;
  return { callee, body: callee.body.body };
}

const nameOf = (node) => node?.name ?? node?.value;

/** An import's or re-export's shape without its names: those are looked up through the other chunk's own exports. */
function importExportShape(text, statement) {
  const source = statement.source ? `from${text.slice(statement.source.start, statement.source.end)}` : "";
  const count = statement.specifiers?.length ?? 0;
  const kind = statement.type === "ImportDeclaration" ? "import" : "export";
  if (statement.type === "ExportAllDeclaration") return `export*${statement.exported ? "as" : ""}${source}`;
  return `${kind}{*${count}}${source}`;
}

/**
 * What a chunk holds: its units (one for each top-level statement and each declarator, order forgotten), its bindings
 * (every name it declares at its top level: where it is declared, where it is used, what it imports) and its exports
 * by name. An export is the unit `export:<the binding>` and an imported name is looked up in the other chunk's exports
 * (`label()`), so the names a minifier gives exports never matter, but what is exported and what is imported does.
 */
function jsUnits(path, text) {
  const body = text; // comments (the source map's among them) are not statements, so the parser leaves them out
  let sourceType = "module";
  let result = parseSync(path, body, { lang: "js", sourceType, preserveParens: false, range: true });
  if (result.errors.length) {
    sourceType = "script";
    result = parseSync(path, body, { lang: "js", sourceType, preserveParens: false, range: true });
  }
  if (result.errors.length) return { units: [{ text: `unparsed:${sha(body)}`, refs: [] }], bindings: [], exports: new Map(), parsed: false };

  // The statements that are units, and the one function a bundled worker is wrapped in.
  const wrappers = new Set();
  const plan = [];
  const collect = (statements) => {
    for (const statement of statements) {
      const wrapped = iifeOf(statement);
      if (wrapped) {
        wrappers.add(wrapped.callee);
        plan.push(null);
        collect(wrapped.body);
      } else {
        plan.push(statement);
      }
    }
  };
  collect(result.program.body);

  const bindings = bindingsOf(result.program, sourceType);
  const list = [];
  const ids = new Map();
  const table = {
    topLevel: (variable) => variable.scope.type === "global" || variable.scope.type === "module" || wrappers.has(variable.scope.block),
    idOf(variable) {
      if (!ids.has(variable)) {
        ids.set(variable, list.length);
        list.push({ declUnits: [], uses: [], import: null });
      }
      return ids.get(variable);
    },
    pseudo(imported) {
      list.push({ declUnits: [], uses: [], import: imported });
      return list.length - 1;
    },
  };
  const exportsByName = new Map();
  const units = [];
  const unit = (made) => units.push(made);
  const declaredBy = (node) => bindings.manager.getDeclaredVariables(node).filter((variable) => table.topLevel(variable));
  const exportUnit = (id) => unit({ text: `export:${MARK}${id}${MARK}`, refs: [{ id, declares: false }] });

  const declaration = (node, exported) => {
    if (node.type === "VariableDeclaration") {
      for (const declarator of node.declarations) {
        const made = patterned(body, declarator, bindings, table);
        unit({ text: `${node.kind} ${made.text}`, refs: made.refs });
      }
    } else {
      unit(patterned(body, node, bindings, table));
    }
    if (!exported) return;
    const named = node.type === "VariableDeclaration" ? declaredBy(node) : declaredBy(node).filter((variable) => node.id && variable.identifiers.includes(node.id));
    for (const variable of named) {
      const id = table.idOf(variable);
      exportsByName.set(variable.name, id);
      exportUnit(id);
    }
  };

  for (const statement of plan) {
    if (statement === null) {
      unit({ text: "iife", refs: [] });
    } else if (statement.type === "VariableDeclaration") {
      declaration(statement, false);
    } else if (statement.type === "ImportDeclaration") {
      unit({ text: importExportShape(body, statement), refs: [] });
      const source = body.slice(statement.source.start, statement.source.end);
      for (const specifier of statement.specifiers) {
        const variable = bindings.occurrence.get(specifier.local);
        if (!variable) continue;
        list[table.idOf(variable)].import =
          specifier.type === "ImportNamespaceSpecifier"
            ? { namespace: true, source }
            : { name: specifier.type === "ImportDefaultSpecifier" ? "default" : nameOf(specifier.imported), source };
      }
    } else if (statement.type === "ExportAllDeclaration") {
      unit({ text: importExportShape(body, statement), refs: [] });
    } else if (statement.type === "ExportNamedDeclaration" && statement.declaration) {
      declaration(statement.declaration, true);
    } else if (statement.type === "ExportNamedDeclaration") {
      unit({ text: importExportShape(body, statement), refs: [] });
      const source = statement.source ? body.slice(statement.source.start, statement.source.end) : null;
      for (const specifier of statement.specifiers) {
        const exported = nameOf(specifier.exported);
        const variable = source ? null : bindings.occurrence.get(specifier.local);
        if (source) {
          const id = table.pseudo({ name: nameOf(specifier.local), source });
          exportsByName.set(exported, id);
          exportUnit(id);
        } else if (variable && table.topLevel(variable)) {
          const id = table.idOf(variable);
          exportsByName.set(exported, id);
          exportUnit(id);
        } else {
          unit({ text: `export:${nameOf(specifier.local)}`, refs: [] });
        }
      }
    } else if (statement.type === "ExportDefaultDeclaration") {
      unit(patterned(body, statement, bindings, table));
      const inner = statement.declaration;
      const named = ["FunctionDeclaration", "ClassDeclaration"].includes(inner?.type) && inner.id ? declaredBy(inner).find((variable) => variable.identifiers.includes(inner.id)) : null;
      exportsByName.set("default", named ? table.idOf(named) : -1);
    } else if (statement.type === "EmptyStatement" || statement.type === "Directive") {
      // nothing to compare
    } else {
      unit(patterned(body, statement, bindings, table));
    }
  }

  units.forEach((made, index) => {
    for (const { id, declares } of made.refs) (declares ? list[id].declUnits : list[id].uses).push(index);
  });
  return { units, bindings: list, exports: exportsByName, parsed: true };
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
      const { units, bindings, exports, parsed } = jsUnits(rel, bytes.toString("utf8"));
      file.kind = "js";
      file.units = units.map((made) => mark(made.text));
      file.bindings = bindings.map((binding) => ({ ...binding, import: binding.import && { ...binding.import, source: mark(binding.import.source) } }));
      file.exports = exports;
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
    file.bindings ??= [];
    file.exports ??= new Map();
    return file;
  });
  return files;
}

const MOST_ROUNDS = 64;
const SETTLED_ROUNDS = 6; // rounds after the last label splits: how far a difference travels along references once all labels are told apart

/** The file a module specifier (`"./index-AbC123.js"`, quotes and marks included) names, or null. */
function targetOf(files, byName, byRel, file, source) {
  const named = [...source.matchAll(REF_PATTERN)].map((m) => m[1]);
  if (named.length === 1 && byName.has(named[0])) return byName.get(named[0]);
  const plain = /^"(\.{1,2}\/[^"]*)"$/.exec(source);
  if (!plain || plain[1].includes(REF)) return null;
  const parts = [...file.rel.split("/").slice(0, -1)];
  for (const part of plain[1].split("/")) {
    if (part === "..") parts.pop();
    else if (part !== ".") parts.push(part);
  }
  return byRel.get(parts.join("/")) ?? null;
}

/**
 * A label for every file and for every top-level binding of every JavaScript file, refined round by round until no
 * label splits any further (the way colours are refined on a graph). A file's label is what it holds and the labels
 * of the files it names; a binding's is what its declaration holds, how it is used, and (for an import) the label of
 * the binding the other chunk exports under that name. Every name in the text is replaced by the label of what it names,
 * so `f(a)` that becomes `f(b)` is a different unit unless `a` and `b` are the same thing under two names.
 */
function label(files) {
  const byName = new Map(files.filter((file) => file.hashed).map((file) => [file.name, file]));
  const byRel = new Map(files.map((file) => [file.rel, file]));
  for (const file of files) {
    file.label = "0";
    for (const binding of file.bindings) {
      binding.label = "0";
      binding.target = binding.import ? targetOf(files, byName, byRel, file, binding.import.source) : null;
    }
  }
  const render = (unit, file) =>
    unit
      .replace(REF_PATTERN, (_, name) => `<${byName.has(name) ? byName.get(name).label : "unknown"}>`)
      .replace(MARK_PATTERN, (_, id) => `[${file.bindings[Number(id)].label}]`);
  const importedLabel = (binding) => {
    const { target } = binding;
    const { name, namespace, source } = binding.import;
    if (target && namespace) return `namespace:${target.label}`;
    if (target && target.exports.has(name)) {
      const id = target.exports.get(name);
      return id === -1 ? `default:${target.label}` : `export:${target.bindings[id].label}`;
    }
    return `unresolved:${name ?? "*"}:${source.replace(REF_PATTERN, "<file>")}`;
  };

  // What a report shows for a name: what its declaration holds, and nothing else, so one edit shows as one edit.
  const plain = (unit) => unit.replace(REF_PATTERN, "<file>").replace(MARK_PATTERN, "$");
  const imports = [];
  for (const file of files) {
    for (const binding of file.bindings) {
      if (binding.import) imports.push(binding);
      else binding.short = sha(binding.declUnits.map((index) => plain(file.units[index])).sort().join("\n")).slice(0, 6);
    }
  }
  for (let pass = 0; pass < 4; pass += 1) {
    for (const binding of imports) {
      const { target } = binding;
      const id = target?.exports.get(binding.import.name);
      binding.short = id !== undefined && id !== -1 ? (target.bindings[id].short ?? "0") : "import";
    }
  }

  let distinct = 0;
  let steady = 0;
  for (let round = 0; round < MOST_ROUNDS; round += 1) {
    for (const file of files) file.hashes = file.units.map((unit) => sha(render(unit, file)));
    const nextBindings = new Map();
    const nextFiles = new Map();
    for (const file of files) {
      for (const binding of file.bindings) {
        const declared = binding.import ? importedLabel(binding) : binding.declUnits.map((index) => file.hashes[index]).sort().join(",");
        const used = binding.uses.map((index) => file.hashes[index]).sort().join(",");
        nextBindings.set(binding, sha(`${binding.label}|${declared}|${used}`));
      }
      const hashes = [...file.hashes];
      if (!file.ordered) hashes.sort();
      nextFiles.set(file, sha(`${file.label}|${file.kind}\n${hashes.join("\n")}`));
    }
    for (const [binding, next] of nextBindings) binding.label = next;
    for (const [file, next] of nextFiles) file.label = next;
    // No label splitting any further says the colouring is settled, not that what each label holds has reached every
    // file that names it: a difference travels one reference a round. So it goes on for a margin of rounds after.
    const count = new Set([...nextBindings.values(), ...nextFiles.values()]).size;
    steady = count === distinct ? steady + 1 : 0;
    distinct = count;
    if (steady >= SETTLED_ROUNDS) break;
  }
  // The text a report shows: what the unit says, each name written as the short label of what it names.
  for (const file of files) {
    file.base = file.units.map((unit) =>
      unit.replace(REF_PATTERN, "<file>").replace(MARK_PATTERN, (_, id) => `$${file.bindings[Number(id)].short}`),
    );
  }
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

/** A row of the `units` listing: what differs, on which side, with a short hash of it. */
function unitRow(file, side, unit) {
  // One row is one line: a unit that holds a line break (a shader, a template) shows it as `\n`.
  const text = readable(unit).replace(/\r/g, "\\r").replace(/\n/g, "\\n").replace(/\t/g, "\\t");
  return { file, side, sha: sha(unit).slice(0, 12), unit: text };
}

/** Every differing unit of a pair of files, uncapped (`compare` shows five a side; this is the whole list). */
function allUnitRows(file, before, after) {
  const { removed, added } = unitDifference(before, after, false);
  const rows = [...removed.map((unit) => unitRow(file, "only before", unit)), ...added.map((unit) => unitRow(file, "only after", unit))];
  if (before.ordered) {
    // The same units in another order is a difference too (a CSS rule moved: the cascade reads in order).
    const gone = multiset(removed);
    const fresh = multiset(added);
    const keep = (units, drop) =>
      units.filter((unit) => {
        const left = drop.get(unit) ?? 0;
        if (left > 0) drop.set(unit, left - 1);
        return left === 0;
      });
    const b = keep(before.base, gone);
    const a = keep(after.base, fresh);
    for (let index = 0; index < Math.max(b.length, a.length); index += 1) {
      if (b[index] === a[index]) continue;
      if (b[index] !== undefined) rows.push(unitRow(file, "only before", `(moved) ${b[index]}`));
      if (a[index] !== undefined) rows.push(unitRow(file, "only after", `(moved) ${a[index]}`));
    }
  }
  return rows;
}

/** A difference that is a whole file, not a unit of one: the file, the side, what it was. */
function fileRows(file, sides, what) {
  return sides.map(([side, label]) => ({ file, side, sha: sha(label).slice(0, 12), unit: `(${what})` }));
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
    if (!other) findings.push({ title: `removed: ${rel} (a file a page asks for by name)`, lines: [], rows: fileRows(rel, [["only before", file.label]], "file removed: a page asks for it by name") });
    else if (other.label !== file.label) findings.push(describeChange(`changed: ${rel}`, file, other));
  }
  for (const [rel, file] of fixedAfter) {
    if (!fixedBefore.has(rel)) findings.push({ title: `added: ${rel} (a file a page asks for by name)`, lines: [], rows: fileRows(rel, [["only after", file.label]], "file added: a page asks for it by name") });
  }

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
      const name = `${file.stem}${file.ext}`;
      findings.push({
        title: `changed: ${name}: the bytes differ (${file.size} before, ${best.size} after)`,
        lines: [],
        rows: fileRows(name, [["only before", file.label], ["only after", best.label]], "the bytes differ"),
      });
    } else {
      findings.push({ title: `removed: ${file.stem}${file.ext} (${file.name}, ${file.size} bytes)`, lines: [], rows: fileRows(`${file.stem}${file.ext}`, [["only before", file.label]], "file removed") });
    }
  }
  for (const file of unmatchedAfter) {
    findings.push({ title: `added: ${file.stem}${file.ext} (${file.name}, ${file.size} bytes)`, lines: [], rows: fileRows(`${file.stem}${file.ext}`, [["only after", file.label]], "file added") });
  }

  findings.sort((a, b) => Number(Boolean(a.knockOn)) - Number(Boolean(b.knockOn)));
  if (findings.length === 0 && before.hash !== after.hash) {
    findings.push({
      title: "the normalised hashes differ though no single file does (a cycle of chunks, or a reference to another file)",
      lines: [],
      rows: fileRows("(build)", [["only before", before.hash], ["only after", after.hash]], "the normalised hashes differ though no single file does"),
    });
  }
  return { before, after, findings };
}

function describeChange(title, before, after) {
  const { removed, added, note } = unitDifference(before, after, before.ordered);
  const file = /^changed: (\S+)/.exec(title)[1];
  if (removed.length === 0 && added.length === 0 && !note) {
    // Nothing in this file changed: it names a file that did, or names another file than it did.
    return {
      title: `${title.replace(/^changed:/, "also differs:")} (it names a file that changed, or names another file)`,
      lines: [],
      knockOn: true,
      rows: fileRows(file, [["only before", before.label], ["only after", after.label]], "names a file that changed, or another file"),
    };
  }
  const lines = [];
  if (note) lines.push(`  ${note}`);
  for (const unit of removed.slice(0, 5)) lines.push(`  - ${readable(unit)}`);
  if (removed.length > 5) lines.push(`  - ... and ${removed.length - 5} more only before`);
  for (const unit of added.slice(0, 5)) lines.push(`  + ${readable(unit)}`);
  if (added.length > 5) lines.push(`  + ... and ${added.length - 5} more only after`);
  return { title, lines, removed, added, rows: allUnitRows(file, before, after) };
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

// ---------------------------------------------------------------------------------------------------- the rebaseline

/** The Mac's one real baseline folder: fixed, and never moved by an environment variable. */
export function realBaseline() {
  return resolve(join(homedir(), "dev/osprey-acceptance/PL4a-baseline/dist"));
}

/** The raw copy of the build before PL4 moved anything: the folder `rebaseline` replaces by default. */
export const DEFAULT_BASELINE = process.env.PL4_BASELINE_DIST ?? realBaseline();

/** The folders only the conductor's merge may replace: the real one, and the one `PL4_BASELINE_DIST` names (the proof's own). */
export function guardedBaselines() {
  return new Set([realBaseline(), resolve(DEFAULT_BASELINE)]);
}

/** The declared units (`<file>\t<side>\t<sha>` of each row; comments and the `against:` line are not rows), as a multiset. */
export function declaredKeys(text) {
  const keys = new Map();
  for (const line of text.split("\n")) {
    if (!line.trim() || line.startsWith("#") || line.startsWith("against: ")) continue;
    const [file, side, unitSha] = line.split("\t");
    const key = `${file}\t${side}\t${unitSha}`;
    keys.set(key, (keys.get(key) ?? 0) + 1);
  }
  return keys;
}

/** The differing rows (as `differingUnits` lists them) with whether each is declared; a declared row is used once. */
export function checkAgainstDeclared(rows, declaredText) {
  const left = declaredKeys(declaredText);
  const checked = rows.map((row) => {
    const key = `${row.file}\t${row.side}\t${row.sha}`;
    const have = left.get(key) ?? 0;
    if (have > 0) left.set(key, have - 1);
    return { row, declared: have > 0 };
  });
  // A declared unit that does not differ is as wrong as an undeclared one that does.
  const missing = [...left].flatMap(([key, count]) => Array(count).fill(key));
  return { checked, missing };
}

function stamp() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "-");
}

function rebaseline(rest) {
  const baseline = resolve(flag(rest, "--baseline") ?? DEFAULT_BASELINE);
  // The real baseline folder is fixed (`realBaseline`), whatever PL4_BASELINE_DIST says, and the folder that variable names
  // is guarded too: only the conductor's merge replaces either (the real one was swapped by hand six times in PL4d3d).
  // Anything else names its own folder with --baseline; the conductor adds --conductor-merge.
  if (guardedBaselines().has(baseline) && !rest.includes("--conductor-merge")) {
    console.log(`REFUSED: ${baseline} is a protected baseline folder (the real one or $PL4_BASELINE_DIST), and only the conductor's merge replaces it: the conductor adds --conductor-merge; anything else passes --baseline <a copy>. Nothing was touched.`);
    return 1;
  }
  const declaredFlag = flag(rest, "--declared");
  if (!declaredFlag) throw new Error("usage: rebaseline --declared <file> [--baseline <folder>] [--dist <built>] [--tests <npm-test-output>] [--out <file>]");
  const declaredPath = resolve(declaredFlag);
  const out = resolve(flag(rest, "--out") ?? join(CORE, "apps/workspace/PL4_BASELINE.json"));
  if (!existsSync(baseline)) throw new Error(`no baseline build at ${baseline}: nothing to replace (set PL4_BASELINE_DIST or pass --baseline)`);
  if (!existsSync(declaredPath)) throw new Error(`no declared-units file at ${declaredPath}`);
  const declaredText = readFileSync(declaredPath, "utf8");

  let fresh = flag(rest, "--dist");
  let scratch = null;
  if (fresh) {
    fresh = resolve(fresh);
  } else {
    scratch = `${baseline}.new-${stamp()}`;
    const built = spawnSync("npm", ["run", "build", "--workspace", "apps/workspace", "--", "--outDir", scratch, "--emptyOutDir"], { cwd: CORE, stdio: "inherit" });
    if (built.status !== 0) throw new Error("npm run build --workspace apps/workspace failed: the baseline is untouched");
    fresh = scratch;
  }
  try {
    const rows = differingUnits(compareBuilds(baseline, fresh).findings);
    const { checked, missing } = checkAgainstDeclared(rows, declaredText);
    console.log(`old baseline ${baseline}\nnew build ${fresh}\n${rows.length} differing unit${rows.length === 1 ? "" : "s"} (old against new):`);
    for (const { row, declared } of checked) console.log(`${row.file}\t${row.side}\t${row.sha}\t${declared ? "declared" : "UNDECLARED"}\t${row.unit.slice(0, 100)}`);
    const undeclared = checked.filter((c) => !c.declared);
    for (const key of missing) console.log(`${key.replaceAll("\t", " ")}\tdeclared but not differing`);
    if (undeclared.length > 0 || missing.length > 0) {
      console.log(`REFUSED: ${undeclared.length} differing unit${undeclared.length === 1 ? " is" : "s are"} neither declared nor knock-on and ${missing.length} declared unit${missing.length === 1 ? "" : "s"} do${missing.length === 1 ? "es" : ""} not differ, in ${declaredPath}; the baseline folder and the record are untouched`);
      return 1;
    }

    let testOutput;
    const testsPath = flag(rest, "--tests");
    if (testsPath) {
      testOutput = readFileSync(testsPath, "utf8");
    } else {
      const ran = spawnSync("npm", ["test", "--workspace", "apps/workspace"], { cwd: CORE, encoding: "utf8", maxBuffer: 1 << 28 });
      testOutput = `${ran.stdout}\n${ran.stderr}`;
      if (ran.status !== 0) {
        console.log("REFUSED: the workspace's unit tests do not pass on this commit (a timeout under load is a rerun); the baseline folder and the record are untouched");
        return 1;
      }
    }
    const record = makeRecord(fresh, testOutput);

    const aside = `${baseline}-before-${stamp()}`;
    renameSync(baseline, aside);
    cpSync(fresh, baseline, { recursive: true });
    const previous = existsSync(out) ? JSON.parse(readFileSync(out, "utf8")) : null;
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, `${JSON.stringify(record, null, 2)}\n`);
    console.log(`the old baseline folder is kept at ${aside}`);
    console.log(`the new build is in ${baseline}`);
    console.log(`wrote ${out}: ${record.files.total} files, hash ${record.normalised_hash.slice(0, 16)} (was ${previous ? previous.normalised_hash.slice(0, 16) : "none"})`);
    return 0;
  } finally {
    if (scratch) rmSync(scratch, { recursive: true, force: true });
  }
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

/**
 * Every difference between two builds, uncapped, in a stable order: the file, the side, the unit's text. A unit of a
 * changed file, and also a whole file added, removed or changed in its bytes (a page's own file, a lazy chunk, an
 * image, a font): every finding of `compareBuilds` has rows, so none is dropped.
 */
export function differingUnits(findings) {
  const rows = findings.flatMap((finding) => {
    if (!finding.rows) throw new Error(`a finding with no rows would be left out of the listing: ${finding.title}`);
    return finding.rows;
  });
  return rows.sort((a, b) => `${a.file}\t${a.side}\t${a.unit}`.localeCompare(`${b.file}\t${b.side}\t${b.unit}`));
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
    case "units": {
      const [before, after] = rest;
      if (!before || !after) throw new Error("usage: units <before-dist> <after-dist>");
      for (const row of differingUnits(compareBuilds(before, after).findings)) console.log(`${row.file}\t${row.side}\t${row.sha}\t${row.unit}`);
      return 0;
    }
    case "rebaseline":
      return rebaseline(rest);
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
      throw new Error("usage: dist_compare.mjs compare|units|rebaseline|normalise|record|verify ...");
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
