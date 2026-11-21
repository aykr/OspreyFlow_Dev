// Builds the service: TypeScript to dist/, then what tsc copies no part of (the Default tree's templates and the
// function list the route modules are checked against), then the browser assets (scripts/assets.mjs).
// The compiler is the one installed for this workspace, found by path: never `npx`, which fetches a
// package of that name from the registry when it is not installed (and `tsc` there is not TypeScript).
import { execFileSync } from "node:child_process";
import { cpSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

import { buildAssets } from "./assets.mjs";

const root = join(import.meta.dirname, "..");
const tsc = createRequire(import.meta.url).resolve("typescript/bin/tsc");
rmSync(join(root, "dist"), { recursive: true, force: true });
execFileSync(process.execPath, [tsc, "-p", "tsconfig.build.json"], { cwd: root, stdio: "inherit" });
cpSync(join(root, "tree-default"), join(root, "dist", "tree-default"), { recursive: true });
cpSync(join(root, "FUNCTIONS.yaml"), join(root, "dist", "FUNCTIONS.yaml"));
await buildAssets({ outDir: join(root, "dist", "assets") });
