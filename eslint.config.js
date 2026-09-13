import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    ignores: ["node_modules/**", "packages/schemas/generated/**", ".venv/**"],
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: { process: "readonly", console: "readonly" },
    },
  },
];
