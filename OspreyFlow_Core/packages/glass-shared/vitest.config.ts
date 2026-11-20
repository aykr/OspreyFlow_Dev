import { defineConfig } from "vitest/config";

// Plain logic, no DOM: the node environment. The workspace's jsdom tests stay in the workspace (a test that
// needs a DOM and React belongs with the React that draws it).
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["**/node_modules/**"],
  },
});
