import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // `*.integration.test.ts` needs the live `make dev-up` stack
    // (ArcadeDB/Valkey/Postgres) — excluded from the default `vitest run`
    // (`npm test`, the fast/no-infra tier) the same way Python's own
    // `make test` excludes its live-infra files; `npm run test:integration`
    // runs it explicitly, from `make test-all`/CI's `conformance` job.
    exclude: ["**/node_modules/**", "**/*.integration.test.ts"],
  },
});
