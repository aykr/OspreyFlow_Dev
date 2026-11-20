// What the two checks of the shared package's isolation (ADR-152 I1 and I13) have in common: finding a tree's
// source files, reading the module names a file imports, and bundling a tree's entry files to see which
// modules they reach.
//
// The bundler is the one the workspace is built with (Vite 8's own, `rolldown`), found from where this script
// lives, so a check run on a scratch tree uses the product's bundler and not one installed beside the scratch
// tree. A check of "what the bundle reaches" is only worth anything if it bundles as the build does.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const requireHere = createRequire(join(HERE, "..", "..", "package.json"));

export const { rolldown } = requireHere("rolldown");
const { parseSync } = requireHere("rolldown/utils");

export const SOURCE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;
export const TEST_FILE = /\.(test|spec)\.[cm]?[jt]sx?$/;
const SKIPPED_DIRECTORIES = new Set(["node_modules", "dist", ".git", "coverage"]);

// Files a bundler is told to leave alone: styles, images, fonts and the like are not code, and a query such as
// `?url` or `?worker` is Vite's, not a module of the tree's.
const NOT_CODE = /\.(css|scss|svg|png|jpe?g|gif|webp|avif|woff2?|ttf|eot|ico|mp4|webm|wasm|pdf)(\?.*)?$|[?](url|raw|worker|inline|sharedworker)\b/;

/** Every file under `directory` (not `node_modules`, `dist` or `.git`) whose name `keep` accepts. */
export function walk(directory, keep = () => true) {
  const found = [];
  let names;
  try {
    names = readdirSync(directory);
  } catch {
    return found;
  }
  for (const name of names.sort()) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(name)) found.push(...walk(path, keep));
    } else if (keep(path)) {
      found.push(path);
    }
  }
  return found;
}

function visit(node, callback) {
  if (Array.isArray(node)) {
    for (const child of node) visit(child, callback);
  } else if (node && typeof node === "object") {
    if (typeof node.type === "string") callback(node);
    for (const key of Object.keys(node)) {
      if (key !== "loc" && key !== "range") visit(node[key], callback);
    }
  }
}

const LANGUAGE = { ts: "ts", mts: "ts", cts: "ts", tsx: "tsx", js: "js", mjs: "js", cjs: "js", jsx: "jsx" };

/**
 * What a source file names: every module it imports or re-exports (type-only forms included, `import("x")` in
 * a type and `require("x")` too), and whether it holds JSX (which compiles to `react/jsx-runtime`).
 * @returns {{ specifiers: string[], jsx: boolean, error: string | null }}
 */
export function readImports(path) {
  const extension = path.slice(path.lastIndexOf(".") + 1);
  const result = parseSync(path, readFileSync(path, "utf8"), { lang: LANGUAGE[extension] ?? "ts" });
  const specifiers = [];
  let jsx = false;
  const literal = (node) => (node && node.type === "Literal" && typeof node.value === "string" ? node.value : null);
  visit(result.program, (node) => {
    let name = null;
    switch (node.type) {
      case "ImportDeclaration":
      case "ExportAllDeclaration":
      case "ExportNamedDeclaration":
        name = literal(node.source);
        break;
      case "ImportExpression":
        name = literal(node.source);
        break;
      case "TSImportType":
        name = literal(node.source) ?? literal(node.argument?.literal);
        break;
      case "TSExternalModuleReference":
        name = literal(node.expression);
        break;
      case "CallExpression":
        if (node.callee?.type === "Identifier" && node.callee.name === "require") name = literal(node.arguments?.[0]);
        break;
      case "JSXElement":
      case "JSXFragment":
        jsx = true;
        break;
      default:
    }
    if (name !== null) specifiers.push(name);
  });
  return { specifiers, jsx, error: result.errors.length ? result.errors[0].message : null };
}

/** The package name in an import specifier or a path through `node_modules`: `@sigma/utils/x` is `@sigma/utils`. */
export function packageNameOf(specifier) {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

/**
 * Bundles `entries` as the build does (no tree-shaking, so an import that is never used still counts) and
 * returns every module they reach. A bare import that resolves to nothing is left external, as the bundler
 * does: that module is not part of the graph, so the source scan, not this, is what names it.
 * @returns {Promise<Set<string>>} the absolute path of every module reached
 */
export async function reachedModules(root, entries) {
  const bundle = await rolldown({
    input: entries,
    cwd: root,
    platform: "browser",
    treeshake: false,
    logLevel: "silent",
    external: (id) => NOT_CODE.test(id),
  });
  const output = await bundle.generate({ format: "esm" });
  await bundle.close();
  const modules = new Set();
  for (const chunk of output.output) {
    if (chunk.type === "chunk") for (const id of chunk.moduleIds) modules.add(id);
  }
  return modules;
}

/** `node_modules/<package>/` in a module path: the last such segment, the package that module belongs to. */
export function packageDirectoryOf(modulePath) {
  const marker = "/node_modules/";
  const at = modulePath.lastIndexOf(marker);
  if (at === -1) return null;
  const rest = modulePath.slice(at + marker.length);
  const name = packageNameOf(rest);
  return { name, directory: modulePath.slice(0, at + marker.length) + name };
}

const ANSI = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, "g");

/**
 * `reachedModules`, but a bundle that cannot be built (a syntax error, a missing export) is a finding and not a
 * crash: it is pushed onto `failures` in one line and `null` comes back, so the check ends in "FAIL" and not in a
 * stack trace, and a tree that does not bundle is never read as one that reaches nothing.
 */
export async function reachedModulesOrFail(root, entries, label, failures) {
  try {
    return await reachedModules(root, entries);
  } catch (error) {
    const lines = String(error?.message ?? error).replace(ANSI, "").split("\n").map((line) => line.trim()).filter(Boolean);
    failures.push(`${label} cannot be bundled, so it cannot be checked: ${lines.slice(0, 2).join(" ")}`);
    return null;
  }
}
