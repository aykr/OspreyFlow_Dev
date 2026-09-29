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
      "apps/harness/dist/**",
      "process/prototypes/**", // the Build folder's, when linted from there (ADR-054)
    ],
  },
  {
    // `apps/workspace/compute-tier1/harness.mjs` (ADR-028's own "small Node script... headless")
    // joined this block 26 September 2026 — a plain Node script like `scripts/**/*.mjs`, just
    // under `apps/workspace/` rather than the repo root, and needing the same globals for the
    // same reason.
    files: [
      "scripts/**/*.mjs",
      "tools/**/*.mjs", // the Build folder's checks, linted from there (ADR-054)
      "apps/workspace/compute-tier1/**/*.mjs",
    ],
    languageOptions: {
      globals: { process: "readonly", console: "readonly" },
    },
  },
  // The Glass (`apps/workspace`) and the setup harness (`apps/harness`, `Stage 2 §6`) — both
  // Vite/React/TypeScript, per `spec/02_GLASS_FRONTEND.md` §1 and `05_DEPLOYMENT.md` §2. One
  // shared `files` glob rather than two near-identical blocks: both packages are the same
  // toolchain by the same ruling (`DECISIONS.md` R1: "the same React/Vite/TypeScript toolchain
  // and design tokens as apps/workspace"). Covers `src/`, `test/` (the delta-client integration
  // harness), `perf/`, `a11y/` and `keyboard/` (the CI-gate Playwright/Vitest suites) — every
  // `.ts`/`.tsx` file in either package, not just the shipped app.
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ["apps/workspace/**/*.{ts,tsx}", "apps/harness/**/*.{ts,tsx}"],
  })),
  {
    files: ["apps/workspace/**/*.{ts,tsx}", "apps/harness/**/*.{ts,tsx}"],
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
