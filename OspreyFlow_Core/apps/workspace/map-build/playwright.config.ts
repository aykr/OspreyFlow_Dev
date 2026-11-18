import { defineConfig } from "@playwright/test";

import { MAP_BUILD_PORT } from "./ports";

const PORT = MAP_BUILD_PORT;

// GG6: `keyboard/map-tiles.spec.ts` again, against a production bundle instead of the dev server.
// MapLibre 6 finds its worker beside the module that loads it, which a Vite production build does not
// emit unless told (ADR-014 Amendment 2), and the dev server cannot show that. The harness page is
// built with `vite build` and served with `vite preview`; the spec is the one `test:keyboard` runs.
export default defineConfig({
  testDir: "../keyboard",
  testMatch: "map-tiles.spec.ts",
  timeout: 60_000,
  webServer: {
    command: `npx vite build --config map-build/vite.config.ts && npx vite preview --config map-build/vite.config.ts --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: process.env.OSPREY_REUSE_SERVER === "1",
    cwd: "..",
    timeout: 180_000,
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
  },
});
