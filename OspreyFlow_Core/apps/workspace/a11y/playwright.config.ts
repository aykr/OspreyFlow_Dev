import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  webServer: {
    command: "node scripts/sync_govuk_assets.mjs && npx vite --port 5184 --strictPort",
    port: 5184,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5184",
  },
});
