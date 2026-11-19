import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** The name of the setting. Written once here and built into the planted files below, so that no file of
 *  the folder holds the name followed by a value. */
export const SECRET_NAME = "OSPREY_PAGES_SESSION_SECRET";

const SKIPPED_FOLDERS = new Set(["node_modules", "dist", ".git"]);
const CODE = /\.(ts|tsx|js|mjs|cjs|njk)$/;

/** Where, never what: a report of a committed secret must not print it. */
export interface Assignment {
  file: string;
  line: number;
}

/**
 * Lines that give the setting a value, in any file shape it could be committed in:
 *  - `NAME=value` (an environment file, a shell line, a compose or Helm list item, `ARG NAME=value`);
 *  - `ENV NAME value` (a Dockerfile);
 *  - `NAME: value` in YAML, JSON, Markdown and the like; and `NAME: "value"` in code.
 * An empty string and a reference are not values: `NAME=$OTHER`, `NAME=${OTHER}`, a bare `ARG NAME`, and in code
 * `NAME: someVariable` or `NAME: generateSecret()` (a test that makes its own at run time).
 */
export function assignmentsIn(file: string, text: string): Assignment[] {
  const name = SECRET_NAME;
  const patterns: RegExp[] = [
    new RegExp(`${name}["']?\\s*=\\s*(?!""|''|[\\s$]|$)\\S`),
    new RegExp(`^\\s*ENV\\s+${name}\\s+(?!""|''|[\\s$]|$)\\S`, "i"),
    new RegExp(`${name}["']?\\s*:\\s*(?:"(?!")|'(?!')|\`(?!\`))`),
  ];
  if (!CODE.test(file)) patterns.push(new RegExp(`${name}["']?\\s*:\\s*(?!""|''|[\\s$]|$)\\S`));
  const found: Assignment[] = [];
  text.split("\n").forEach((line, index) => {
    if (patterns.some((p) => p.test(line))) found.push({ file, line: index + 1 });
  });
  return found;
}

/** Every file of the folder (the Dockerfile included), but not installed packages or build output. */
export function filesUnder(root: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(root)) {
    if (SKIPPED_FOLDERS.has(entry)) continue;
    const path = join(root, entry);
    if (statSync(path).isDirectory()) out.push(...filesUnder(path));
    else out.push(path);
  }
  return out;
}

/** The lines, in all files of the folder, that give the setting a value. */
export function scanTree(root: string): Assignment[] {
  return filesUnder(root).flatMap((path) =>
    assignmentsIn(relative(root, path), readFileSync(path, "utf8")),
  );
}
