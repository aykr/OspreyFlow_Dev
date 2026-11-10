import { defineConfig } from "@playwright/test";

import { lanePort } from "../../lanePorts";

// This lane's own port (T2, `OspreyFlow_Build/scripts/lane_ports.tsv`): 5184 on main.
const PORT = lanePort(5184);

export default defineConfig({
  testDir: ".",
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
