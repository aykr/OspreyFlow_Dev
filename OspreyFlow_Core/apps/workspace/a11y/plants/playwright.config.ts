import { defineConfig } from "@playwright/test";

import { lanePort } from "../../../lanePorts";

// The contrast probe's guard plants (the orchestrator's review of T3b at 9697ad3, item 1): run only
// through `node a11y/plants/run.mjs`, which writes the probe's guard-removed variants first. Its own
// `testMatch`, so the a11y config's runs, and CI's, never pick a plant up.
const PORT = lanePort(5184);

export default defineConfig({
  testDir: ".",
  testMatch: "*.plant.ts",
  timeout: 300_000,
  workers: 1,
  webServer: {
    command: `node scripts/sync_govuk_assets.mjs && npx vite --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "../..",
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
  },
});
