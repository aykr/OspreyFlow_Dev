import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

// What `packages/glass-shared` must never name (ADR-152 I1 and I13, D46): no React, so `pages` can use it, and no drawing library,
// so each front end binds its own. Value or type: `allowTypeImports: false`, because a bundler drops a type-only import and
// `scripts/version_isolation_check.mjs` therefore cannot see one; this rule is the only thing that does.
const SHARED_BANNED_NAMES = [
  ["react", "no React in the shared package (I1)"],
  ["react-dom", "no React in the shared package (I1)"],
  ["sigma", "the shared package imports no drawing library (I13, D46)"],
  ["maplibre-gl", "the shared package imports no drawing library (I13, D46)"],
];
const SHARED_BANNED_PATTERNS = [
  ["react/*", "no React in the shared package (I1)"],
  ["react-dom/*", "no React in the shared package (I1)"],
  ["sigma/*", "the shared package imports no drawing library (I13, D46)"],
  ["@sigma/*", "the shared package imports no drawing library (I13, D46)"],
  ["maplibre-gl/*", "the shared package imports no drawing library (I13, D46)"],
];
// `import("sigma").Map` in a type position, and `import("sigma")` as an expression, are not import statements, so the rule
// above does not see them.
// The slash is escaped because the selector's own regular expression ends at the first plain one.
const SHARED_BANNED_MODULE = "^(react|react-dom|sigma|maplibre-gl|@sigma)($|\\/)";

export default [
  js.configs.recommended,
  {
    ignores: [
      "node_modules/**",
      "**/node_modules/**",
      "packages/schemas/generated/**",
      ".venv/**",
      "apps/workspace/dist/**",
      "apps/workspace/map-build/dist/**",
      "apps/harness/dist/**",
      "apps/pages/dist/**",
      "packages/glass-shared/dist/**",
      "deploy/generated/**", // a deployment's rendered files, copies of what is linted at its source
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
      "apps/harness/scripts/**/*.mjs",
      "apps/pages/scripts/**/*.mjs",
    ],
    languageOptions: {
      globals: { process: "readonly", console: "readonly" },
    },
  },
  {
    // The plain ES5 scripts put into pages that are not React as they are (the sign-in page's
    // form and the light/dark cookie, ADR-072): browser globals, and `catch (e)` kept, since ES5
    // has no catch without a binding.
    files: ["harness/**/*.js"],
    languageOptions: {
      sourceType: "script",
      globals: { document: "readonly", window: "readonly", location: "readonly" },
    },
    rules: { "no-unused-vars": ["error", { caughtErrors: "none" }] },
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
  // The shared package (ADR-152 decision 6): plain TypeScript, TypeScript's recommended rules, and the import ban above.
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ["packages/glass-shared/**/*.{ts,tsx,mts,cts}"],
  })),
  {
    files: ["packages/glass-shared/**/*.{ts,tsx,mts,cts}"],
    languageOptions: { globals: { console: "readonly", process: "readonly" } },
    rules: {
      // TypeScript's own compiler catches an undefined identifier, as for the workspace.
      "no-undef": "off",
      // The core rule cannot tell a type import from a value import; the TypeScript one can, and is told to
      // refuse both.
      "no-restricted-imports": "off",
      "@typescript-eslint/no-restricted-imports": [
        "error",
        {
          paths: SHARED_BANNED_NAMES.map(([name, message]) => ({ name, message, allowTypeImports: false })),
          patterns: SHARED_BANNED_PATTERNS.map(([group, message]) => ({ group: [group], message, allowTypeImports: false })),
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: `TSImportType Literal[value=/${SHARED_BANNED_MODULE}/]`,
          message: "The shared package names no React and no drawing library, not even in a type (I1, I13).",
        },
        {
          selector: `ImportExpression > Literal[value=/${SHARED_BANNED_MODULE}/]`,
          message: "The shared package imports no React and no drawing library (I1, I13), not even by a dynamic import.",
        },
      ],
    },
  },
];
