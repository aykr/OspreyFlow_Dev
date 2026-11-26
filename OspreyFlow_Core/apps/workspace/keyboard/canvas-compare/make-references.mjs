// Makes the canvas-look comparison's references (slice WS4a; `keyboard/canvas-compare.spec.ts`), and records who made
// them, why, on which machine and from which commit in `REFERENCES.json`. The only way a reference is written: the
// spec refuses a reference this record does not bear out.
//
//   npm run canvas-compare:references --workspace apps/workspace -- --reason "<why the look is meant to change>"
//
// Refused with no reason, in CI, or from a tree with uncommitted changes to the canvas's own files (a reference made
// from a look nobody can find again proves nothing). Commit the pictures and the record together, with the reason in
// the commit message.
import { execFileSync, spawnSync } from "node:child_process";
import console from "node:console";
import process from "node:process";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { arch, cpus, platform, release } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = join(HERE, "..", "..");

const at = process.argv.indexOf("--reason");
const reason = at >= 0 ? (process.argv[at + 1] ?? "").trim() : "";
if (!reason || reason.startsWith("--")) {
  console.error('refused: give the reason the references are made: -- --reason "<why the look is meant to change>"');
  process.exit(2);
}
if (process.env.CI) {
  console.error("refused: references are never made in CI; make them on a named machine and commit them");
  process.exit(2);
}
const git = (...args) => execFileSync("git", args, { cwd: WORKSPACE, encoding: "utf8" }).trim();
const dirty = git(
  "status", "--porcelain", "--", "src/canvas", "src/export", "src/map", "../../packages/glass-shared/src/canvas",
  "keyboard/canvas-compare-harness.tsx", "keyboard/canvas-compare.spec.ts", "keyboard/canvasCompare.ts", "keyboard/pngPixels.ts",
);
if (dirty) {
  console.error(`refused: the canvas's own files have uncommitted changes, so the look the references record could not be found again:\n${dirty}`);
  process.exit(2);
}

const run = spawnSync("npx", ["playwright", "test", "--config", "keyboard/canvas-compare.config.ts", "--workers=1"], {
  cwd: WORKSPACE,
  stdio: "inherit",
  env: { ...process.env, CANVAS_COMPARE_WRITE: "1", CANVAS_COMPARE_REASON: reason },
});
if (run.status !== 0) {
  console.error("the references were not all made; nothing is recorded");
  process.exit(run.status ?? 1);
}

const browser = spawnSync("node", ["-e", "import('@playwright/test').then(async ({ chromium }) => { const b = await chromium.launch(); console.log(b.version()); await b.close(); })"], {
  cwd: WORKSPACE,
  encoding: "utf8",
});
const scenes = {};
for (const file of readdirSync(HERE).filter((f) => f.endsWith(".png")).sort()) {
  scenes[file.replace(/\.png$/, "")] = createHash("sha256").update(readFileSync(join(HERE, file))).digest("hex");
}
const record = {
  made_at: new Date().toISOString(),
  made_by: git("config", "user.name"),
  reason,
  commit: git("rev-parse", "HEAD"),
  machine: {
    platform: `${platform()} ${release()} ${arch()}`,
    cpu: cpus()[0]?.model ?? "unknown",
    node: process.version,
    chromium: browser.stdout.trim() || "unknown",
    // As the browser names it, read by the spec while it drew (`renderer.txt`, removed below).
    webgl: readFileSync(join(HERE, "renderer.txt"), "utf8").trim(),
    scale: "device scale 1",
  },
  scenes,
};
rmSync(join(HERE, "renderer.txt"));
writeFileSync(join(HERE, "REFERENCES.json"), `${JSON.stringify(record, null, 2)}\n`);
console.log(`made ${Object.keys(scenes).length} references; commit them with REFERENCES.json and the reason: ${reason}`);
