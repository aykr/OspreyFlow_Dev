import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default [
  js.configs.recommended,
  {
    ignores: [
      "node_modules/**",
      "**/node_modules/**",
      "packages/schemas/generated/**",
      ".venv/**",
      "apps/workspace/dist/**",
      "prototypes/**",
    ],
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: { process: "readonly", console: "readonly" },
    },
  },
  // The Glass (`apps/workspace`) — Vite/React/TypeScript, per
  // `docs/02_GLASS_FRONTEND.md` §1. Scoped to `apps/workspace` rather than
  // added globally since no other TypeScript source exists yet. Covers
  // `src/`, `test/` (the delta-client integration harness), `perf/` and
  // `a11y/` (the CI-gate Playwright suites) — every `.ts`/`.tsx` file in
  // the package, not just the shipped app.
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ["apps/workspace/**/*.{ts,tsx}"],
  })),
  {
    files: ["apps/workspace/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    languageOptions: {
      parserOptions: { ecmaFeatures: { jsx: true } },
      // TypeScript's own compiler already catches a genuinely undefined
      // identifier, more accurately than a hand-maintained globals list —
      // `no-undef` on top of that only produces false positives for
      // DOM/browser globals (`document`, `MouseEvent`, `fetch`, ...).
      globals: { console: "readonly", process: "readonly" },
    },
    rules: {
      "no-undef": "off",
      ...reactHooks.configs.recommended.rules,
    },
  },
];
