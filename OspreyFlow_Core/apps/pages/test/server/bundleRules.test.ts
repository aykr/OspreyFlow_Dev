/**
 * Slice IS5a0, round 3: the bundle's "no drawing library" refusal (ADR-152 decision 9; the brief's item 4 says no React and
 * no drawing library in a pages bundle). `apps/pages/scripts/assets.mjs`'s rules plugin refuses `sigma`, `@sigma/*` and `maplibre-gl`
 * until a slice that draws names the library in `ALLOWED_DRAWING`. `no_react_check.mjs` has no drawing rule, and the shared
 * package's own isolation check does not read `modules/`, so this is the only test that would fail if the refusal were removed.
 *
 * The planted modules are written here, at the shape a module has (a `.ts` file in `modules/` importing the package as a
 * browser module does), and built through `buildAssets`, the call the build step really makes. The allowance case shows the
 * refusal is by name: with the library's name on the list the same module is no longer refused for being a drawing library.
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

type Built = { manifest: Record<string, string>; outDir: string };
interface Builder {
  buildAssets: (options: { outDir: string; modulesDir?: string }) => Promise<Built>;
  ALLOWED_DRAWING: string[];
}

const WORDS = /a drawing library is not bundled until a slice that draws allows it by name.*ADR-152 decision 9/s;

let root = "";
let assets: Builder;

/** A modules folder holding one module with this body. */
function plant(name: string, body: string): string {
  const folder = join(root, `modules-${name}`);
  mkdirSync(folder, { recursive: true });
  writeFileSync(join(folder, `${name}.ts`), body);
  return folder;
}

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "pages-bundle-rules-"));
  assets = (await import("../../scripts/assets.mjs")) as Builder;
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("the bundle refuses a drawing library", () => {
  it.each([
    ["maplibre", "maplibre-gl", 'import maplibregl from "maplibre-gl";\ndocument.title = String(maplibregl.version);\n'],
    ["maplibreSub", "maplibre-gl/dist/maplibre-gl.js", 'import "maplibre-gl/dist/maplibre-gl.js";\n'],
    ["sigma", "sigma", 'import Sigma from "sigma";\ndocument.title = String(Sigma);\n'],
    ["sigmaScoped", "@sigma/node-border", 'import { NodeBorderProgram } from "@sigma/node-border";\ndocument.title = String(NodeBorderProgram);\n'],
  ])("a module importing %s (%s) fails the build, in words naming the importer", async (name, specifier, body) => {
    const modulesDir = plant(name, body);
    const attempt = assets.buildAssets({ outDir: join(root, `out-${name}`), modulesDir });
    await expect(attempt).rejects.toThrow(WORDS);
    await expect(attempt).rejects.toThrow(new RegExp(specifier.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")));
    await expect(attempt).rejects.toThrow(new RegExp(`${name}\\.ts`));
  }, 60_000);

  it("starts with no library allowed, so the refusals above are the default and not a test's setting", () => {
    expect(assets.ALLOWED_DRAWING).toEqual([]);
  });

  it("refuses by name: with the names on the allowance list the same import is not refused as a drawing library", async () => {
    const modulesDir = plant("allowed", 'import { NodeBorderProgram } from "@sigma/node-border";\ndocument.title = String(NodeBorderProgram);\n');
    // The scoped package itself imports `sigma/rendering`, so a slice that draws names both, by the first path segment.
    assets.ALLOWED_DRAWING.push("@sigma", "sigma");
    try {
      let message = "";
      try {
        await assets.buildAssets({ outDir: join(root, "out-allowed"), modulesDir });
      } catch (error) {
        message = String((error as Error).message);
      }
      expect(message).not.toMatch(/drawing library/);
    } finally {
      assets.ALLOWED_DRAWING.splice(0);
    }
    // And with the list empty again the same module is refused, so the allowance, not the module, made the difference.
    await expect(assets.buildAssets({ outDir: join(root, "out-allowed-again"), modulesDir })).rejects.toThrow(WORDS);
  }, 60_000);
});
