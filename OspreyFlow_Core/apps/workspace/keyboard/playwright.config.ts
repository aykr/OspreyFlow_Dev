import { defineConfig } from "@playwright/test";

import { lanePort } from "../../lanePorts";

// This lane's own port (T2, `OspreyFlow_Build/scripts/lane_ports.tsv`): 5185 on main.
const PORT = lanePort(5185);

export default defineConfig({
  testDir: ".",
  // Phase 7 Stage 4's `registryCoverage.test.ts` (a Vitest test, `npm test`'s own fast tier, not
  // a browser walkthrough — see its own header) shares this directory for the first time.
  // Playwright's default `testMatch` picks up `*.test.ts` as readily as `*.spec.ts`, and Vitest's
  // `describe`/`it` are not this runner's globals — scoped here so the two suites never collide
  // over the same file.
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  webServer: {
    command: `node scripts/sync_govuk_assets.mjs && npx vite --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "..",
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
  },
});
