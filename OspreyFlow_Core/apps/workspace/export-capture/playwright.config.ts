import { defineConfig } from "@playwright/test";

import { lanePort } from "../../lanePorts";

// This lane's own port (T2, `OspreyFlow_Build/scripts/lane_ports.tsv`): 5186 on main.
const PORT = lanePort(5186);

// A real Chromium instance with a real WebGL context — the one thing this project's own vitest
// environment cannot give `chartExport.ts::captureChartImage` (its own module docstring has the
// full "why not vitest" reasoning). Same shape as `perf/playwright.config.ts`: a standalone Vite
// entry, `webServer` starts it itself, `npm run test:export-capture` needs nothing pre-running.
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "..",
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
  },
});
