import { defineConfig } from "@playwright/test";

import { lanePort } from "../../lanePorts";

// This lane's own port (T2, `OspreyFlow_Build/scripts/lane_ports.tsv`): 5183 on main.
const PORT = lanePort(5183);

// `spec/02_GLASS_FRONTEND.md` §5/§6's CI gates (perf regression proxy +
// automated contrast check) — a separate Playwright project from the
// vitest unit suites, since these need a real (if software-rendered)
// browser. `webServer` starts Vite itself, so `npm run test:perf` needs
// nothing pre-running.
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
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
