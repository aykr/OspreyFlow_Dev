import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import SlowestReporter from "../workspace/src/testing/slowestReporter";

export default defineConfig({
  plugins: [react()],
  test: {
    // Every run ends with its 30 slowest tests (admin's T1 part 1), as pytest's --durations=30 does.
    reporters: ["default", new SlowestReporter()],
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "keyboard/**/*.test.ts"],
  },
});
