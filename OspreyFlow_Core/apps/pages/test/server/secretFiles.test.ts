/**
 * The owner's rule for `OSPREY_PAGES_SESSION_SECRET` (19 November 2026): no value for it is committed
 * anywhere in the service's own files, an example environment file, the Dockerfile, a README or a test.
 * The scan reads every file of the folder and fails if any gives the name a value. It is shown red
 * (rule 15) by planting, in the shapes a value is committed in, files that do.
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { generateSecret } from "../support/secret.js";
import { SECRET_NAME, filesUnder, scanTree } from "../support/secretScan.js";

const PAGES = fileURLToPath(new URL("../..", import.meta.url));

describe("no value for the session secret is committed in apps/pages", () => {
  it("is true of every file of the folder, the Dockerfile included", () => {
    const files = filesUnder(PAGES).map((f) => f.slice(PAGES.length));
    // The scan reaches what it claims to: the Dockerfile, the sources, the tests and the manifest.
    expect(files).toContain("Dockerfile");
    expect(files).toContain("server/config.ts");
    expect(files).toContain("package.json");
    expect(files.some((f) => f.startsWith("test/server/"))).toBe(true);
    expect(files.some((f) => f.includes("node_modules"))).toBe(false);
    expect(scanTree(PAGES)).toEqual([]);
  });
});

describe("the scan itself: a planted value is found, in the shape it would be committed in", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "pages-secret-scan-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  const plant = (file: string, text: string): void => {
    mkdirSync(dirname(join(dir, file)), { recursive: true });
    writeFileSync(join(dir, file), text);
  };

  // The planted values are the shape of a real one, not a convenient string that fails a different way, and made now,
  // at random, so that no secret-shaped string is committed in this file either (the owner, 20 November 2026).
  const value = generateSecret(32);
  const cases: Array<[string, string, string]> = [
    ["an example environment file", ".env.example", `${SECRET_NAME}=${value}\n`],
    ["a sample environment file with quotes", "env.sample", `${SECRET_NAME}="${value}"\n`],
    ["an exported shell line", "run.sh", `export ${SECRET_NAME}=${value}\n`],
    ["a Dockerfile ENV with an equals sign", "Dockerfile", `FROM node:22-slim\nENV ${SECRET_NAME}=${value}\n`],
    ["a Dockerfile ENV with a space", "Dockerfile", `FROM node:22-slim\nENV ${SECRET_NAME} ${value}\n`],
    ["a Dockerfile ARG with a default", "Dockerfile", `FROM node:22-slim\nARG ${SECRET_NAME}=${value}\n`],
    ["a compose file", "deploy/compose.yaml", `services:\n  pages:\n    environment:\n      ${SECRET_NAME}: ${value}\n`],
    ["a compose list item", "deploy/compose.yml", `    environment:\n      - ${SECRET_NAME}=${value}\n`],
    ["a Helm values file", "chart/values.yaml", `env:\n  ${SECRET_NAME}: "${value}"\n`],
    ["a README", "README.md", `Set ${SECRET_NAME}: ${value} before starting.\n`],
    ["a JSON file", "settings.json", `{ "${SECRET_NAME}": "${value}" }\n`],
    ["a test fixture, in code", "test/fixtures/env.ts", `export const env = { ${SECRET_NAME}: "${value}" };\n`],
    ["a template literal in code", "test/x.test.ts", `const env = { ${SECRET_NAME}: \`${value}\` };\n`],
  ];

  it.each(cases)("finds %s", (_name, file, text) => {
    plant(file, text);
    const found = scanTree(dir);
    expect(found.map((f) => f.file)).toEqual([file]);
    expect(found[0]?.line).toBeGreaterThan(0);
  });

  it("reports where a value is, and never the value", () => {
    plant(".env.example", `${SECRET_NAME}=${value}\n`);
    expect(JSON.stringify(scanTree(dir))).not.toContain(value);
  });

  it("finds a value planted in a copy of the real folder's layout, beside files that are clean", () => {
    plant("Dockerfile", `FROM node:22-slim\n# ${SECRET_NAME} is a run-time setting\nUSER 10001:10001\n`);
    plant("server/config.ts", `const secret = env["${SECRET_NAME}"];\n`);
    expect(scanTree(dir)).toEqual([]);
    plant("deploy/.env.example", `${SECRET_NAME}=${value}\n`);
    expect(scanTree(dir).map((f) => f.file)).toEqual(["deploy/.env.example"]);
  });

  it("does not find installed packages or build output, and does not mind references and mentions", () => {
    plant("node_modules/x/.env", `${SECRET_NAME}=${value}\n`);
    plant("dist/server/x.js", `const a = { ${SECRET_NAME}: "${value}" };\n`);
    plant("Dockerfile", `ARG ${SECRET_NAME}\nENV ${SECRET_NAME}=$FROM_OUTSIDE\n`);
    plant("compose.yaml", `      - ${SECRET_NAME}=\${FROM_OUTSIDE}\n`);
    plant("test/a.test.ts", `const env = { ${SECRET_NAME}: secret, other: 1 };\nconst e2 = { ${SECRET_NAME}: generateSecret(31) };\n`);
    plant("test/b.test.ts", `loadConfig({ ${SECRET_NAME}: "" });\n`);
    plant(".env.example", `${SECRET_NAME}=\n`);
    plant("compose.yml", `      ${SECRET_NAME}: ""\n`);
    plant("README.md", `The service needs ${SECRET_NAME} (at least 32 characters) and refuses to start without it.\n`);
    expect(scanTree(dir)).toEqual([]);
  });
});
