/**
 * The Studio pages' plain helpers are held to the shared package's (slice IS5a).
 *
 * `server/views/studioWords.ts` writes a few functions once more than `packages/glass-shared` has them, because the server's
 * `NodeNext` build cannot import the shared package's extension-less source (the file's header says so). This test is what
 * keeps the copies honest: each is run on the same inputs as the shared one, and a copy that drifts is red.
 *
 * Which test fails if a copy drifts (rule 12): `studioDatasets`, `currentDataset`, `caseForDataset`, `modelInWords` and
 * `releaseName` and the Needs-you words (`reminder`, `reminderTip`, `unreadProposals`), each by name below; the planted case at the end shows the comparison itself can fail (rule 15).
 */
import { beforeAll, describe, expect, it } from "vitest";

import { NEEDS_YOU_WORDS, caseForDataset, currentDataset, modelInWords, releaseName, studioDatasets } from "../../server/views/studioWords.js";
import type { CaseListing as SharedCase } from "../../server/views/studioWords.js";

/**
 * The shared package, loaded when the test runs and named by a variable, so that the compiler does not read it: it cannot
 * (its files have no extensions on their relative imports, which `NodeNext` needs), and that is the reason this test exists.
 * The test runner resolves it as any package.
 */
interface Shared {
  caseForDataset(cases: readonly SharedCase[], datasetId: string, currentId: string | null): string | null;
  currentDataset(cases: readonly SharedCase[], caseId: string | null): string | null;
  modelInWords(packs: readonly string[] | undefined): string;
  releaseName(datasetName: string): string;
  studioDatasets(cases: readonly SharedCase[], currentId: string | null): { id: string; name: string }[];
  NEEDS_YOU_WORDS: { reminder(n: number): string; reminderTip: string; unreadProposals: string };
}
const SHARED = "@ospreyflow/glass-shared";
let shared: Shared;
beforeAll(async () => {
  shared = (await import(/* @vite-ignore */ SHARED)) as Shared;
});

const cases: SharedCase[] = [
  { id: "c1", name: "Wing", level: "viewer", created_at: "2026-11-01T09:00:00Z", created_by: "a", datasets: ["One"], dataset_ids: ["d1"], domains: ["niem"] },
  { id: "c2", name: "Block", level: "author", created_at: "2026-11-02T09:00:00Z", created_by: "a", datasets: ["One"], dataset_ids: ["d1"], domains: [] },
  { id: "c3", name: "Yard", level: "editor", created_at: "2026-11-03T09:00:00Z", created_by: "a", datasets: ["Two"], dataset_ids: ["d2"], domains: ["fibo", "stix"] },
  { id: "c4", name: "Bare", level: "author", created_at: "2026-11-04T09:00:00Z", created_by: "a", datasets: [], dataset_ids: [], domains: [] },
  { id: "c5", name: "No name for it", level: "viewer", created_at: "2026-11-05T09:00:00Z", created_by: "a", dataset_ids: ["d3"] },
];

describe("the pages' helpers answer as the shared package's do", () => {
  it("studioDatasets: each dataset once, the open case's first", () => {
    for (const current of [null, "c1", "c3", "c4", "c5", "missing"]) {
      expect(studioDatasets(cases, current)).toEqual(shared.studioDatasets(cases, current));
    }
  });

  it("currentDataset: the case's first dataset, or none", () => {
    for (const current of [null, "c1", "c4", "c5", "missing"]) {
      expect(currentDataset(cases, current)).toBe(shared.currentDataset(cases, current));
    }
  });

  it("caseForDataset: the open case when it loads into it, else the highest level, else none", () => {
    for (const current of [null, "c1", "c2", "c3", "missing"]) {
      for (const dataset of ["d1", "d2", "d3", "nope"]) {
        expect(caseForDataset(cases, dataset, current)).toBe(shared.caseForDataset(cases, dataset, current));
      }
    }
  });

  it("modelInWords: the core, then each pack in the catalogue's order", () => {
    for (const packs of [undefined, [], ["niem"], ["stix", "fibo"], ["niem", "fibo", "stix"], ["unknown"]]) {
      expect(modelInWords(packs)).toBe(shared.modelInWords(packs));
    }
  });

  it("releaseName: a name as Kubernetes takes one", () => {
    for (const name of ["Prison Intelligence — 2026", "  ", "Harbour prison extract (synthetic)", "x".repeat(90), "A.b-C"]) {
      expect(releaseName(name)).toBe(shared.releaseName(name));
    }
  });

  it("NEEDS_YOU_WORDS: the reminder for any count, its tip, and the line for a count that could not be read", () => {
    for (const n of [0, 1, 2, 7, 120]) expect(NEEDS_YOU_WORDS.reminder(n)).toBe(shared.NEEDS_YOU_WORDS.reminder(n));
    expect(NEEDS_YOU_WORDS.reminderTip).toBe(shared.NEEDS_YOU_WORDS.reminderTip);
    expect(NEEDS_YOU_WORDS.unreadProposals).toBe(shared.NEEDS_YOU_WORDS.unreadProposals);
  });

  it("a Needs-you word that drifted would be caught: the comparison can fail", () => {
    const drifted = { ...NEEDS_YOU_WORDS, reminderTip: `${NEEDS_YOU_WORDS.reminderTip} Changed.` };
    expect(drifted.reminderTip).not.toBe(shared.NEEDS_YOU_WORDS.reminderTip);
    expect(drifted.reminder(2)).toBe(shared.NEEDS_YOU_WORDS.reminder(2));
  });

  it("a copy that drifted would be caught: the comparison can fail", () => {
    const drifted = (current: string | null) => studioDatasets(cases, current).slice(1);
    expect(drifted("c1")).not.toEqual(shared.studioDatasets(cases, "c1"));
  });
});
