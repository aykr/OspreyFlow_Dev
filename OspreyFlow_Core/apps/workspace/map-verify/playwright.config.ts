import { defineConfig } from "@playwright/test";

import { lanePort } from "../../lanePorts";

// This lane's own port (T2, `OspreyFlow_Build/scripts/lane_ports.tsv`): 5185 on main.
const PORT = lanePort(5185);

// `spec/00_ARCHITECTURE.md` §1.2.1's contrast-floor Verify check — a
// separate Playwright project from `a11y/`'s (a different port, so both
// can run without colliding), mirroring `a11y/playwright.config.ts`'s own
// shape exactly.
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
