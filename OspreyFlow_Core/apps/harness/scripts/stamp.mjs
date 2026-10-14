// Writes dist/source.sha256 after a build (ADR-114 Amendment 11): a hash of the sources the guided
// install page is built from, so `ospreyflow install --gui` can tell a page built from this checkout
// from a stale one. `harness/install_page_build.py` computes the same hash; a test holds them equal.
//
// The hash: every file under SOURCES (relative to the product folder, `/`-separated, skipping
// dotfiles, node_modules and macOS's `Icon\r`), sorted by path; for each, `path\n<sha256 of the
// file>\n`; the SHA-256 of all of that.
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const SOURCES = [
  "apps/harness/src",
  "apps/harness/index.html",
  "apps/harness/package.json",
  "apps/workspace/src/design",
  "apps/workspace/src/theme",
];

const skipped = (name) => name.startsWith(".") || name === "node_modules" || name === "Icon\r";

function files(product, path) {
  const full = join(product, path);
  if (statSync(full).isFile()) return [path];
  return readdirSync(full)
    .filter((name) => !skipped(name))
    .flatMap((name) => files(product, join(path, name)));
}

export function sourceHash(product) {
  const paths = SOURCES.flatMap((source) => files(product, source))
    .map((path) => path.split(sep).join("/"))
    .sort();
  const all = createHash("sha256");
  for (const path of paths) {
    const digest = createHash("sha256").update(readFileSync(join(product, path))).digest("hex");
    all.update(`${path}\n${digest}\n`);
  }
  return all.digest("hex");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const product = process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
  const hash = sourceHash(product);
  writeFileSync(join(product, "apps/harness/dist/source.sha256"), `${hash}\n`);
  console.log(`stamped the install page: ${hash.slice(0, 12)} (${relative(process.cwd(), product) || "."})`);
}
