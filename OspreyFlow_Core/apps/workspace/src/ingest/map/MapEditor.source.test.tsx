// @vitest-environment jsdom
//
// ADR-140 Amendment 6 (the owner's ruling, "Name source, mask as pipeline"): Map's left pane says which
// registered source the pipeline reads, and its version, but its fields are still the pipeline's own
// profile — the same file under the source's governance, masked also by any marking the pipeline sets
// above the source's (ADR-127 decision 3). The source's own profile route, which knows only the
// source's marking, is never read here: reading it would show a reader values Map masks for them.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchProfile } from "../api";
import { listSources, sourceProfile } from "../sources/api";
import { MapScreen } from "./MapScreen";

const DRAFT = {
  recipe_id: "r1", label: "Cell stays", row_template: null, unmapped_fields: [], dataset_id: "ds-a",
  source_location: "ds-a/cell_stays.csv",
  handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
};  // prettier-ignore
const SOURCE = {
  id: "s1", dataset_id: "ds-a", connection_id: "files", name: "Cell stays file", location: "ds-a/cell_stays.csv",
  connector_profile: "generic-csv", handling: DRAFT.handling, legal_basis: "Synthetic", refresh: { trigger: "manual" },
  version: 2, created_by: "e", created_at: "",
};  // prettier-ignore

let draft: Record<string, unknown> = DRAFT;
let sources: unknown = [SOURCE];

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchDraft: vi.fn(async () => draft),
    fetchProfile: vi.fn(async () => ({ columns: [{ name: "prisoner", sample_size: 2, null_count: 0, distinct_count: 2,
      inferred_type: "string", type_confidence: 1, sample_values: ["▒▒▒-▒"] }] })),  // prettier-ignore
    fetchOntologySchema: vi.fn(async () => ({ version: 1, entity_types: [], edge_types: [] })),
    fetchTransforms: vi.fn(async () => []),
    fetchHandlingScheme: vi.fn(async () => ({ classifications: [], handling_codes: [] })),
    fetchSampleRow: vi.fn(async () => null),
  };
});
vi.mock("../sources/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../sources/api")>();
  return {
    ...actual,
    listSources: vi.fn(async () => {
      if (sources instanceof Error) throw sources;
      return sources;
    }),
    sourceProfile: vi.fn(async () => {
      throw new Error("Map must not read the source's own profile");
    }),
  };
});
vi.mock("./MapCanvas", () => ({ MapCanvas: () => null }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  draft = DRAFT;
  sources = [SOURCE];
});

async function mount(): Promise<HTMLElement> {
  render(<MapScreen apiBaseUrl="" investigationId="inv-1" bearerToken="tok" recipeId="r1" onBack={() => undefined} />);
  await screen.findByText("+ entity");
  return screen.getByRole("heading", { name: "Source fields" }).closest("section")!;
}

describe("Map's left pane and the registered source", () => {
  it("names the registered source and its version, and shows the pipeline's own profile", async () => {
    const pane = await mount();
    expect(await screen.findByText("From the registered source Cell stays file, version 2.")).toBeTruthy();
    expect(pane.textContent).toContain("prisoner");
    expect(vi.mocked(listSources)).toHaveBeenCalledWith(expect.anything(), "ds-a");
    expect(vi.mocked(fetchProfile)).toHaveBeenCalled();
    expect(vi.mocked(sourceProfile)).not.toHaveBeenCalled();
  });

  it("says so when no registered source reads the pipeline's file", async () => {
    sources = [{ ...SOURCE, location: "ds-a/other.csv" }];
    await mount();
    expect(await screen.findByText("No registered source reads this file: its settings are the pipeline's own.")).toBeTruthy();
  });

  it("says so when the registered sources cannot be read, rather than naming none", async () => {
    sources = new Error("refused");
    await mount();
    expect(await screen.findByText("The registered sources could not be read.")).toBeTruthy();
  });

  it("says nothing of sources for a pipeline in no dataset", async () => {
    draft = { ...DRAFT, dataset_id: null };
    await mount();
    expect(vi.mocked(listSources)).not.toHaveBeenCalled();
    expect(screen.queryByText(/registered source/)).toBeNull();
  });
});
