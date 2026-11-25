// The copy guards' kit (`copyTextsTestKit.ts`) walks once per test file and parses each text once (PL4h). This holds
// that the sharing changes nothing the two guards check: the same files are walked as a fresh walk of the disc finds, a
// plant's copy is listed as the disc lists it, and a second walk or parse is the first one's, not a new one.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import {
  copyTexts,
  discWalkCount,
  GUARD_TEST_TIMEOUT_MS,
  plantedLinkClients,
  movedClients,
  MOVED_FOLDERS,
  plantedCopy,
  ROOTS,
  SHARED_SRC,
  sourceFiles,
  SRC,
  walkedOnce,
  walkOnDisc,
} from "./copyTextsTestKit";

// Which tests walk afresh, and why: the kit's hook walks the two real roots once, and a plant's copy is listed from that
// walk, so a test that asks for `sourceFiles()`, `movedClients()` or a plant's `sourceFiles([root])` reads it and pays none.
// A test that must walk a folder on disc itself (`walkOnDisc`: the check that the shared walk is what the disc says) or a
// temporary one the hook did not walk pays those walks, and says so in its own timeout: each is a few milliseconds alone, up
// to four a test, and the planted fault of PL4h makes a walk take 6 s, as a loaded server can, so these tests are given 30 s,
// each its own and never raised for the suite or the config.
const FRESH_WALKS_MS = 30_000;

/** Vitest's own limit for a test that declares none: the config here sets no `testTimeout`. */
const VITEST_DEFAULT_TIMEOUT_MS = 5_000;

describe("the copy guards' kit shares one walk and one parse and changes what is read in nothing", () => {
  it("walks the same files as a fresh walk of each root on disc finds", () => {
    for (const root of ROOTS) expect(walkOnDisc(root).length, root).toBeGreaterThan(50);
    // The shared walk of both roots is the roots' own fresh walks, one after the other (no walk of one root alone: it
    // would be a second walk, with its own key).
    expect(sourceFiles()).toEqual(ROOTS.flatMap((root) => walkOnDisc(root)));
  }, FRESH_WALKS_MS);

  it("finds the moved clients as a fresh walk of the shared package on disc finds them", () => {
    const fresh = walkOnDisc(SHARED_SRC).filter((path) => MOVED_FOLDERS.test(path));
    expect(fresh.length).toBeGreaterThanOrEqual(6);
    expect(movedClients()).toEqual(fresh);
  }, FRESH_WALKS_MS);

  it("lists a workspace file, a shared file, and none of the tests, kits or generated types", () => {
    const walked = sourceFiles();
    expect(walked.some((path) => path.startsWith(SRC))).toBe(true);
    expect(walked.some((path) => path.startsWith(SHARED_SRC))).toBe(true);
    expect(walked.filter((path) => /\.(test|spec)\.|TestKit\.ts$|\/generated\/|\/node_modules\//.test(path))).toEqual([]);
  });

  it("asks the walk once for each list of roots, however many times it is read", () => {
    let calls = 0;
    const walk = walkedOnce((roots = []) => {
      calls += 1;
      return roots.map((root) => `${root}/a.ts`);
    });
    expect(walk(["/kit-count/one"])).toEqual(["/kit-count/one/a.ts"]);
    expect(walk(["/kit-count/one"])).toEqual(["/kit-count/one/a.ts"]);
    expect(walk(["/kit-count/one"])).toEqual(["/kit-count/one/a.ts"]);
    expect(calls).toBe(1);
    expect(walk(["/kit-count/two"])).toEqual(["/kit-count/two/a.ts"]);
    expect(calls).toBe(2);
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
  }, FRESH_WALKS_MS);

  it("hands each caller its own list, so one test cannot change what another walks", () => {
    const first = sourceFiles();
    first.length = 0;
    expect(sourceFiles().length).toBeGreaterThan(50);
  });

  it("lists a plant's copy as the disc lists it, and the plant's file is among them", () => {
    const planted = plantedCopy("updateNotice.ts", 'export const PLANTED = { note: "a placeholder value" };');
    try {
      const onDisc = walkOnDisc(planted.root);
      // The copy's list is the shared walk's, re-rooted: the same files as the disc lists, whatever order it lists them in.
      expect([...sourceFiles([planted.root])].sort()).toEqual([...onDisc].sort());
      expect(onDisc.map((path) => relative(planted.root, path))).toContain(planted.file);
      expect(onDisc.map((path) => relative(planted.root, path)).sort()).toEqual(
        walkOnDisc(SHARED_SRC)
          .map((path) => relative(SHARED_SRC, path))
          .sort(),
      );
    } finally {
      planted.remove();
    }
  }, FRESH_WALKS_MS);

  it("lists a plant's copy from the shared walk: no walk of the copy, and the very files of the shared package re-rooted", () => {
    sourceFiles();
    const before = discWalkCount();
    const planted = plantedLinkClients('export const PLANTED = { note: "a placeholder value" };');
    try {
      const listed = sourceFiles([planted.root]);
      expect(discWalkCount(), "a plant walked the disc").toBe(before);
      const shared = sourceFiles().filter((path) => path.startsWith(SHARED_SRC));
      expect(listed.map((path) => relative(planted.root, path)).sort()).toEqual(
        shared.map((path) => relative(SHARED_SRC, path)).sort(),
      );
      // Every listed file is really there, and the plant is in each of the link clients.
      expect(listed.length).toBeGreaterThan(50);
      expect(planted.files.every((file) => listed.includes(join(planted.root, file)))).toBe(true);
    } finally {
      planted.remove();
    }
  });

  it("gives a test its limit only when the test passes it: importing the kit changes no other test's", (context) => {
    expect(GUARD_TEST_TIMEOUT_MS).toBeGreaterThan(VITEST_DEFAULT_TIMEOUT_MS);
    // This test passes no limit, so it has vitest's own, though the kit is imported (PL4h round 5: the kit once raised it
    // for every test of every file that imports it, `auth/resolvedPrincipal.test.ts` included).
    expect(context.task.timeout).toBe(VITEST_DEFAULT_TIMEOUT_MS);
  });

  it("carries a limit that a test passes as its own argument", (context) => {
    expect(context.task.timeout).toBe(GUARD_TEST_TIMEOUT_MS);
  }, GUARD_TEST_TIMEOUT_MS);

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
  }, FRESH_WALKS_MS);

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

  it("parses a source once: the same source read again is the very same result, not a new parse", () => {
    const source = 'export const once = "read only once";';
    const first = copyTexts("once.ts", source);
    // `toBe` is identity: a second parse would be an equal array, but not this one.
    expect(copyTexts("once.ts", source)).toBe(first);
    expect(copyTexts("elsewhere/once.ts", source)).toBe(first);
    expect(copyTexts("once.ts", `${source}\nexport const more = "a changed source";`)).not.toBe(first);
  });
});
