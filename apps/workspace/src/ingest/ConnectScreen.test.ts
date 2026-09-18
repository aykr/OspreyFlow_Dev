import { describe, expect, it } from "vitest";

import type { ConnectorCatalogueEntry, StudioRecipeDraft } from "../../../../packages/schemas/generated";
import { draftToForm, formToInput, groupCatalogue } from "./ConnectScreen";

// This project has no React Testing Library / jsdom setup anywhere yet
// (`vitest.config.ts`'s `environment: "node"`, no rendering test exists to
// mirror) — introducing one for a single screen would be new test
// infrastructure, not reuse of an existing pattern. What's tested here
// instead is the screen's pure logic: form <-> API-shape conversion and
// catalogue grouping. The screen itself is verified live in the browser
// (`docs/09_INGEST_STUDIO.md` §2's three gate questions, checked by hand).

function draft(overrides: Partial<StudioRecipeDraft> = {}): StudioRecipeDraft {
  return {
    recipe_id: "recipe-1",
    version: 1,
    status: "draft",
    label: "Carrier A — CDR",
    connector_profile: "generic-csv",
    source_location: "s3://bucket/carrier-a.csv",
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    legal_basis: "RIPA s22 acquisition — authorisation 2026/0114",
    owning_unit: "unit-1",
    created_by: "analyst-1",
    created_at: "2026-01-01T00:00:00Z",
    ready_for_profile: true,
    ...overrides,
  };
}

describe("groupCatalogue", () => {
  it("groups entries by their group, preserving first-seen order", () => {
    const entries: ConnectorCatalogueEntry[] = [
      { id: "a", label: "A", group: "Generic", structured: true, available: true },
      { id: "b", label: "B", group: "Financial", structured: true, available: false },
      { id: "c", label: "C", group: "Generic", structured: true, available: false },
    ];

    const grouped = groupCatalogue(entries);

    expect(grouped.map(([group]) => group)).toEqual(["Generic", "Financial"]);
    expect(grouped[0][1].map((e) => e.id)).toEqual(["a", "c"]);
  });
});

describe("draftToForm / formToInput round trip", () => {
  it("reads a fully-answered draft back into the form", () => {
    const form = draftToForm(draft());

    expect(form.connectorProfile).toBe("generic-csv");
    expect(form.sourceLocation).toBe("s3://bucket/carrier-a.csv");
    expect(form.classification).toBe("OFFICIAL");
    expect(form.handlingCode).toBe("P");
    expect(form.legalBasis).toBe("RIPA s22 acquisition — authorisation 2026/0114");
  });

  it("converts a partially-answered form into null, not empty-string, gaps", () => {
    const form = draftToForm(
      draft({ source_location: null, legal_basis: null, handling: {}, ready_for_profile: false }),
    );

    const input = formToInput(form);

    expect(input.source_location).toBeNull();
    expect(input.legal_basis).toBeNull();
    expect(input.handling).toEqual({});
  });

  it("round-trips a fully-answered form back into equivalent API input", () => {
    const original = draft();
    const input = formToInput(draftToForm(original));

    expect(input.label).toBe(original.label);
    expect(input.connector_profile).toBe(original.connector_profile);
    expect(input.source_location).toBe(original.source_location);
    expect(input.legal_basis).toBe(original.legal_basis);
    expect(input.handling).toEqual(original.handling);
  });
});
