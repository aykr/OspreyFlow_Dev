// Builds the service: TypeScript to dist/, then what tsc copies no part of (the Default tree's templates and the
// function list the route modules are checked against), then the browser assets (scripts/assets.mjs).
// The compiler is the one installed for this workspace, found by path: never `npx`, which fetches a
// package of that name from the registry when it is not installed (and `tsc` there is not TypeScript).
import { execFileSync } from "node:child_process";
import { cpSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

import { buildAssets } from "./assets.mjs";

const root = join(import.meta.dirname, "..");
// `--out <folder>` writes the build there instead of to `dist/` (the layout is the same: a test builds to a scratch folder and
// runs what it wrote). The default is the folder the image copies.
const flag = process.argv.indexOf("--out");
if (flag !== -1 && !process.argv[flag + 1]) throw new Error("--out needs a folder");
const out = flag === -1 ? join(root, "dist") : resolve(process.argv[flag + 1]);
const tsc = createRequire(import.meta.url).resolve("typescript/bin/tsc");
rmSync(out, { recursive: true, force: true });
execFileSync(process.execPath, [tsc, "-p", "tsconfig.build.json", "--outDir", out], { cwd: root, stdio: "inherit" });
cpSync(join(root, "tree-default"), join(out, "tree-default"), { recursive: true });
cpSync(join(root, "FUNCTIONS.yaml"), join(out, "FUNCTIONS.yaml"));
await buildAssets({ outDir: join(out, "assets") });
