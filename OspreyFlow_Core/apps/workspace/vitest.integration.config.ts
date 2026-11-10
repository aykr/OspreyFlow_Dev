import { defineConfig } from "vitest/config";

import SlowestReporter from "./src/testing/slowestReporter";

// A separate config, not an `--exclude` CLI override of `vitest.config.ts`
// — vitest's CLI `--exclude` *adds to* the configured `exclude` array
// rather than replacing it, so there is no CLI-only way to un-exclude
// `*.integration.test.ts` from the default config. This file's `include`
// simply never mentions the default config's exclusion in the first
// place. Run via `npm run test:integration`, which needs the live
// `make dev-up` stack — see `deltaClient.integration.test.ts`'s own
// module docstring.
export default defineConfig({
  test: {
    // Every run ends with its 30 slowest tests (admin's T1 part 1), as pytest's --durations=30 does.
    reporters: ["default", new SlowestReporter()],
    environment: "node",
    include: ["src/**/*.integration.test.ts"],
  },
});
