// The production bundle of the map-tiles harness page alone, for `map-build/playwright.config.ts`
// (slice GG6): `vite build --config map-build/vite.config.ts`, then `vite preview` over `map-build/dist`.
// Built from `apps/workspace` as its root so the page keeps the path it has under the dev server,
// `/keyboard/map-tiles-harness.html`, and the same spec runs against either. Everything else is the
// product's own `vite.config.ts` (mode `production`; its build fence on a dev bearer token included).
import { resolve } from "node:path";

import { defineConfig, mergeConfig } from "vite";

import product from "../vite.config.ts";

const root = resolve(import.meta.dirname, "..");

export default defineConfig((env) =>
  mergeConfig(typeof product === "function" ? product(env) : product, {
    root,
    // The product's own base ("/"), so a bundle served here is addressed as the deployed one is.
    build: {
      outDir: resolve(root, "map-build/dist"),
      emptyOutDir: true,
      rollupOptions: { input: resolve(root, "keyboard/map-tiles-harness.html") },
    },
  }),
);
