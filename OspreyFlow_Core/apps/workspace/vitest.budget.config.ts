import { defineConfig } from "vitest/config";

import base, { BUDGET_TESTS } from "./vitest.config";

// The performance-budget tests, run after the rest of `npm test` and on their own: one file at a
// time, so what is timed is the code under test and not the other files beside it
// (`vitest.config.ts`'s `exclude` has the measurement). The budget itself is unchanged.
export default defineConfig({
  ...base,
  test: {
    ...base.test,
    include: [BUDGET_TESTS],
    exclude: ["**/node_modules/**"],
    fileParallelism: false,
  },
});
