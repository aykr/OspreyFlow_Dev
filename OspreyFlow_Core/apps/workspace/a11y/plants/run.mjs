// Runs the contrast probe's guard plants (the orchestrator's review of T3b at 9697ad3, item 1):
//
//   cd OspreyFlow_Core/apps/workspace && node a11y/plants/run.mjs [playwright args…]
//
// It writes each variant in `variants.mjs` (the probe with one guard removed) into a fresh folder under
// the system's temporary directory, outside the repository (so neither `eslint .` nor a commit ever
// sees one), runs `*.plant.ts` under this folder's own config with that folder in
// `OSPREY_PLANT_VARIANTS`, and deletes it again. A plant passes when every probe, the real one and each
// variant, gives the outcome the plant records for it.
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { VARIANTS } from "./variants.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const judgement = join(HERE, "..", "..", "src", "color", "textContrast");
const probe = readFileSync(join(HERE, "..", "undecidedContrast.ts"), "utf8");

const out = mkdtempSync(join(tmpdir(), "osprey-plant-variants-"));
let code = 1;
try {
  for (const [name, edits] of Object.entries(VARIANTS)) {
    let text = probe.replace(`from "../src/color/textContrast"`, () => `from ${JSON.stringify(judgement)}`);
    for (const [from, to] of edits) {
      const count = text.split(from).length - 1;
      if (count !== 1) throw new Error(`variant ${name}: its edit matches ${count} times, not once: ${from.slice(0, 80)}`);
      text = text.replace(from, () => to);
    }
    writeFileSync(join(out, `${name}.ts`), `// A variant of the probe for the plants only, deleted after the run.\n${text}`);
  }
  const run = spawnSync("npx", ["playwright", "test", "--config", join(HERE, "playwright.config.ts"), ...process.argv.slice(2)], {
    stdio: "inherit",
    env: { ...process.env, OSPREY_PLANT_VARIANTS: out },
  });
  code = run.status ?? 1;
} finally {
  rmSync(out, { recursive: true, force: true });
}
process.exit(code);
