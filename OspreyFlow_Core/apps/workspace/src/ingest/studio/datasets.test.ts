import { describe, expect, it } from "vitest";

import type { CaseListing } from "../../investigation/cases";
import { caseForDataset, currentDataset, studioDatasets } from "./datasets";

function listing(id: string, ids: string[], extra: Partial<CaseListing> = {}): CaseListing {
  return {
    id,
    name: id,
    level: "editor",
    created_at: "2026-11-05T00:00:00Z",
    created_by: "osprey-demo-engineer",
    dataset_ids: ids,
    datasets: ids.map((d) => `Dataset ${d}`),
    ...extra,
  };
}

const CASES = [
  listing("case-a", ["ds-1", "ds-2"]),
  listing("case-b", ["ds-2"], { level: "viewer" }),
  listing("case-c", ["ds-2"], { level: "author" }),
  listing("case-d", ["ds-3"]),
];

describe("the Studio's datasets", () => {
  it("offers each dataset a case loads into once, the current case's first", () => {
    expect(studioDatasets(CASES, "case-d").map((d) => d.id)).toEqual(["ds-3", "ds-1", "ds-2"]);
  });

  it("does not offer a dataset a case only reads, since a load would go elsewhere", () => {
    const only = [listing("case-a", ["ds-1", "ds-9"])];
    expect(studioDatasets(only, "case-a").map((d) => d.id)).toEqual(["ds-1"]);
  });

  it("names the dataset the current case loads into", () => {
    expect(currentDataset(CASES, "case-a")).toBe("ds-1");
    expect(currentDataset(CASES, "nowhere")).toBeNull();
  });

  it("keeps the current case when the dataset is the one it loads into", () => {
    expect(caseForDataset(CASES, "ds-1", "case-a")).toBe("case-a");
  });

  it("chooses the higher level first for another dataset", () => {
    expect(caseForDataset(CASES, "ds-2", "case-a")).toBe("case-c");
  });

  it("chooses no case for a dataset none of the person's cases loads into", () => {
    expect(caseForDataset(CASES, "ds-9", "case-a")).toBeNull();
    // ds-1 is read by case-a only as its first; a case reading it second would not do.
    expect(caseForDataset([listing("case-x", ["ds-2", "ds-1"])], "ds-1", null)).toBeNull();
  });
});
