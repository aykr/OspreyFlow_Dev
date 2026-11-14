import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import SlowestReporter from "./src/testing/slowestReporter";

/** The files that time a performance budget; `vitest.budget.config.ts` runs them, one at a time. */
export const BUDGET_TESTS = "src/**/*.budget.test.{ts,tsx}";

export default defineConfig({
  // Needed from Phase 7 Stage 6c Part 2 on, for `src/**/*.test.tsx`'s own `@testing-library/react`
  // component-render tests (`watches/*.test.tsx`) — every `*.test.ts` before this stage was pure
  // logic and never needed JSX transformed. Same plugin `vite.config.ts` already uses for the app
  // itself, not a second, divergent JSX pipeline.
  plugins: [react()],
  test: {
    // Every run ends with its 30 slowest tests (admin's T1 part 1), as pytest's --durations=30 does.
    reporters: ["default", new SlowestReporter()],
    environment: "node",
    // ADR-115 E4: a desktop-sized window for jsdom tests (`src/testSetup.ts`).
    setupFiles: ["src/testSetup.ts"],
    // `compute-tier1/**/*.test.mjs`: Phase 7 Stage 3's Tier 1 harness is a plain Node script run
    // outside Vite/`tsconfig.json`'s own `include` (the same "outside `src/`, untyped, standalone"
    // shape `keyboard/`/`a11y/` already have) — its own adversarial unit test still needs a runner.
    // `keyboard/**/*.test.ts`: Phase 7 Stage 4's static registry-coverage gate
    // (`keyboard/registryCoverage.test.ts`) — a plain import-and-grep check, not a Playwright
    // walkthrough, so it belongs in the fast/no-infra tier `npm test` already runs, not
    // `test:keyboard`'s own browser suite.
    // `src/**/*.test.tsx`: component-render tests, opted into `jsdom` per-file via a
    // `// @vitest-environment jsdom` docblock rather than changing the `environment` above —
    // every existing `*.test.ts` stays on the faster, DOM-less `node` environment unaffected.
    include: [
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
      "compute-tier1/**/*.test.mjs",
      "keyboard/**/*.test.ts",
    ],
    // `*.integration.test.ts` needs the live `make dev-up` stack
    // (ArcadeDB/Valkey/Postgres) — excluded from the default `vitest run`
    // (`npm test`, the fast/no-infra tier) the same way Python's own
    // `make test` excludes its live-infra files; `npm run test:integration`
    // runs it explicitly, from `make test-all`/CI's `conformance` job.
    // `*.budget.test.{ts,tsx}` holds every timed case under `src/`: §5's first-frame budget
    // (`02_GLASS_FRONTEND.md` §5, a CI gate by rule 10) and the unit limits beside it. They run
    // alone: `npm test` runs them second, by `vitest.budget.config.ts`, one file at a time. Inside
    // this run the Matrix budget shared the CPU with 369 other files and read 3245–3428 ms where it
    // reads ~1240 ms alone (13 November 2026, CI run 43426503300 and this Mac), and settledAnchors
    // read 1535 ms against its 1000 (14 November 2026, `make test` on a loaded server): measures of
    // the neighbours, not of the code. `src/testing/budgetRun.test.ts` fails if a budget file is in
    // neither run, or a timed case is left in an ordinary test file.
    exclude: ["**/node_modules/**", "**/*.integration.test.ts", BUDGET_TESTS],
  },
});
