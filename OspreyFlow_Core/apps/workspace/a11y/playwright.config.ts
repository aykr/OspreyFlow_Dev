import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  webServer: {
    command: "npx vite --port 5184 --strictPort",
    port: 5184,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
  },
  use: {
    baseURL: "http://localhost:5184",
  },
});
