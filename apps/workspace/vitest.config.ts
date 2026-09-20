import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // `compute-tier1/**/*.test.mjs`: Phase 7 Stage 3's Tier 1 harness is a plain Node script run
    // outside Vite/`tsconfig.json`'s own `include` (the same "outside `src/`, untyped, standalone"
    // shape `keyboard/`/`a11y/` already have) — its own adversarial unit test still needs a runner.
    include: ["src/**/*.test.ts", "compute-tier1/**/*.test.mjs"],
    // `*.integration.test.ts` needs the live `make dev-up` stack
    // (ArcadeDB/Valkey/Postgres) — excluded from the default `vitest run`
    // (`npm test`, the fast/no-infra tier) the same way Python's own
    // `make test` excludes its live-infra files; `npm run test:integration`
    // runs it explicitly, from `make test-all`/CI's `conformance` job.
    exclude: ["**/node_modules/**", "**/*.integration.test.ts"],
  },
});
