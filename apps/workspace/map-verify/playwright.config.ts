import { defineConfig } from "@playwright/test";

// `docs/00_ARCHITECTURE.md` §1.2.1's contrast-floor Verify check — a
// separate Playwright project from `a11y/`'s (a different port, so both
// can run without colliding), mirroring `a11y/playwright.config.ts`'s own
// shape exactly.
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  webServer: {
    command: "npx vite --port 5185 --strictPort",
    port: 5185,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5185",
  },
});
