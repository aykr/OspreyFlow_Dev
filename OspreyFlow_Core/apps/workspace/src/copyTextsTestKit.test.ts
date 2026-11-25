// The copy guards' kit (`copyTextsTestKit.ts`) walks once per test file and parses each text once (PL4h). This holds
// that the sharing changes nothing the two guards check: the same files are walked as a fresh walk of the disc finds, a
// plant's copy is listed as the disc lists it, and a second walk or parse is the first one's, not a new one.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { copyTexts, movedClients, MOVED_FOLDERS, plantedCopy, ROOTS, SHARED_SRC, sourceFiles, SRC, walkOnDisc } from "./copyTextsTestKit";

describe("the copy guards' kit shares one walk and one parse and changes what is read in nothing", () => {
  it("walks the same files as a fresh walk of each root on disc finds", () => {
    for (const root of ROOTS) {
      const fresh = walkOnDisc(root);
      expect(fresh.length, root).toBeGreaterThan(50);
      expect(sourceFiles([root])).toEqual(fresh);
    }
    expect(sourceFiles()).toEqual(ROOTS.flatMap((root) => walkOnDisc(root)));
  });

  it("finds the moved clients as a fresh walk of the shared package on disc finds them", () => {
    const fresh = walkOnDisc(SHARED_SRC).filter((path) => MOVED_FOLDERS.test(path));
    expect(fresh.length).toBeGreaterThanOrEqual(6);
    expect(movedClients()).toEqual(fresh);
  });

  it("lists a workspace file, a shared file, and none of the tests, kits or generated types", () => {
    const walked = sourceFiles();
    expect(walked.some((path) => path.startsWith(SRC))).toBe(true);
    expect(walked.some((path) => path.startsWith(SHARED_SRC))).toBe(true);
    expect(walked.filter((path) => /\.(test|spec)\.|TestKit\.ts$|\/generated\/|\/node_modules\//.test(path))).toEqual([]);
  });

  it("walks a list of roots once: a file added after the first walk is not listed again, a fresh walk lists it", () => {
    const root = mkdtempSync(join(tmpdir(), "copy-kit-"));
    try {
      writeFileSync(join(root, "a.ts"), "export const a = 1;\n");
      expect(sourceFiles([root])).toEqual([join(root, "a.ts")]);
      writeFileSync(join(root, "b.ts"), "export const b = 2;\n");
      expect(sourceFiles([root])).toEqual([join(root, "a.ts")]);
      expect(walkOnDisc(root).sort()).toEqual([join(root, "a.ts"), join(root, "b.ts")]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("hands each caller its own list, so one test cannot change what another walks", () => {
    const first = sourceFiles();
    first.length = 0;
    expect(sourceFiles().length).toBeGreaterThan(50);
  });

  it("lists a plant's copy as the disc lists it, and the plant's file is among them", () => {
    const planted = plantedCopy("updateNotice.ts", 'export const PLANTED = { note: "a placeholder value" };');
    try {
      const onDisc = walkOnDisc(planted.root);
      expect(sourceFiles([planted.root])).toEqual(onDisc);
      expect(onDisc.map((path) => relative(planted.root, path))).toContain(planted.file);
      expect(onDisc.map((path) => relative(planted.root, path)).sort()).toEqual(
        walkOnDisc(SHARED_SRC)
          .map((path) => relative(SHARED_SRC, path))
          .sort(),
      );
    } finally {
      planted.remove();
    }
  });

  it("forgets a plant's copy when it is removed, so a later walk of that folder is a new one", () => {
    const planted = plantedCopy("updateNotice.ts", 'export const PLANTED = { note: "a placeholder value" };');
    planted.remove();
    mkdirSync(planted.root);
    try {
      writeFileSync(join(planted.root, "c.ts"), "export const c = 3;\n");
      expect(sourceFiles([planted.root])).toEqual([join(planted.root, "c.ts")]);
    } finally {
      rmSync(planted.root, { recursive: true, force: true });
    }
  });

  it("parses what each source says, not what an earlier source said, and a .tsx apart from a .ts", () => {
    const one = copyTexts("a.ts", 'export const a = "first words";');
    const two = copyTexts("b.ts", 'export const b = "second words";');
    expect(one.map((text) => text.words)).toEqual(["first words"]);
    expect(two.map((text) => text.words)).toEqual(["second words"]);
    expect(copyTexts("c.ts", 'export const a = "first words";')).toEqual(one);
    const jsx = "export const View = () => <span>shown text</span>;";
    expect(copyTexts("View.tsx", jsx).map((text) => text.words)).toContain("shown text");
    expect(copyTexts("View.ts", jsx).map((text) => text.words)).not.toContain("shown text");
  });
});
