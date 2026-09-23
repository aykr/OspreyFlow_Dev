import { defineConfig } from "@playwright/test";

// A real Chromium instance with a real WebGL context — the one thing this project's own vitest
// environment cannot give `chartExport.ts::captureChartImage` (its own module docstring has the
// full "why not vitest" reasoning). Same shape as `perf/playwright.config.ts`: a standalone Vite
// entry, `webServer` starts it itself, `npm run test:export-capture` needs nothing pre-running.
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  webServer: {
    command: "npx vite --port 5186 --strictPort",
    port: 5186,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5186",
  },
});
