// Runs the contrast probe's guard plants (the orchestrator's review of T3b at 9697ad3, item 1):
//
//   cd OspreyFlow_Core/apps/workspace && node a11y/plants/run.mjs [playwright args…]
//
// It writes each variant in `variants.mjs` (the probe with one guard removed) into `.variants/`, runs
// `*.plant.ts` under this folder's own config, and deletes `.variants/` again, so neither `eslint .`
// nor a commit ever sees them. A plant passes when every probe, the real one and each variant, gives
// the outcome the plant records for it.
import { spawnSync } from "node:child_process";
import process from "node:process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { VARIANTS } from "./variants.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, ".variants");
const probe = readFileSync(join(HERE, "..", "undecidedContrast.ts"), "utf8");

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT);
let code = 1;
try {
  for (const [name, edits] of Object.entries(VARIANTS)) {
    let text = probe.replace(`from "../src/color/textContrast"`, `from "../../../src/color/textContrast"`);
    for (const [from, to] of edits) {
      const count = text.split(from).length - 1;
      if (count !== 1) throw new Error(`variant ${name}: its edit matches ${count} times, not once: ${from.slice(0, 80)}`);
      text = text.replace(from, () => to);
    }
    writeFileSync(join(OUT, `${name}.ts`), `// A variant of the probe for the plants only, deleted after the run.\n${text}`);
  }
  const run = spawnSync("npx", ["playwright", "test", "--config", join(HERE, "playwright.config.ts"), ...process.argv.slice(2)], { stdio: "inherit" });
  code = run.status ?? 1;
} finally {
  rmSync(OUT, { recursive: true, force: true });
}
process.exit(code);
