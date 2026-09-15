import { defineConfig } from "@playwright/test";

// `docs/02_GLASS_FRONTEND.md` §5/§6's CI gates (perf regression proxy +
// automated contrast check) — a separate Playwright project from the
// vitest unit suites, since these need a real (if software-rendered)
// browser. `webServer` starts Vite itself, so `npm run test:perf` needs
// nothing pre-running.
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  webServer: {
    command: "npx vite --port 5183 --strictPort",
    port: 5183,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5183",
  },
});
