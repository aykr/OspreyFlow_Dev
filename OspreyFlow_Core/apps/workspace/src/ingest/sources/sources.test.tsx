// @vitest-environment jsdom
// ADR-140 Amendment 4 (redesign phase 3), the Glass: what would fail if each part were wrong — the
// wizard registering before its governance is complete, or sending something other than what was
// chosen; Back losing nothing; the source page's governance edit not saying which deployed pipelines
// now need attention; a pipeline's source chooser not writing the source's marking to the draft.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SourceTable, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { RegisterSourceWizard } from "./RegisterSourceWizard";
import { SourceChooser } from "./SourceChooser";
import { SourcePage } from "./SourcePage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const API = { apiBaseUrl: "http://api", bearerToken: "t" };
const SCHEME = { name: "uk", classification: ["OFFICIAL", "SECRET"], handling_codes: { P: { label: "Permitted", dissemination: "permitted" as const } } };
const HANDLING = { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" };
const SOURCE: SourceTable = {
  id: "s1", dataset_id: "ds-a", connection_id: "files", name: "Cell stays", location: "/in/ds-a/cells.csv",
  connector_profile: "generic-csv", handling: HANDLING, legal_basis: "Synthetic", refresh: { trigger: "manual" },
  version: 1, created_by: "eng-1", created_at: "2026-11-06T09:00:00Z",
};  // prettier-ignore

type Call = { path: string; method: string; body: unknown };
function serve(routes: Record<string, unknown>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      const method = init?.method ?? "GET";
      calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      const key = `${method} ${path}`;
      const found = key in routes ? routes[key] : undefined;
      return { ok: found !== undefined, status: found === undefined ? 404 : 200, json: async () => found ?? {} } as Response;
    }),
  );
  return calls;
}

describe("the register wizard", () => {
  it("goes Connection, File, Governance, refuses to register until governance is complete, and sends what was chosen", async () => {
    const calls = serve({
      "GET /v1/ingest/connections": [{ id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" }],
      "GET /v1/datasets/ds-a/source-files": { root: "/in", files: [{ name: "cells.csv", source_location: "/in/ds-a/cells.csv", size_bytes: 1, modified_at: 1 }] },
      "POST /v1/datasets/ds-a/sources": SOURCE,
    });
    const onRegistered = vi.fn();
    render(<RegisterSourceWizard api={API} datasetId="ds-a" scheme={SCHEME} registered={[]} onRegistered={onRegistered} onCancel={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Next" }));
    fireEvent.change(await screen.findByRole("combobox", { name: "File" }), { target: { value: "/in/ds-a/cells.csv" } });
    expect((screen.getByRole("textbox", { name: "Source name" }) as HTMLInputElement).value).toBe("cells.csv");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("button", { name: "Register" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Still to give: a classification/)).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Classification" }), { target: { value: "OFFICIAL" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Handling code" }), { target: { value: "P" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Originator" }), { target: { value: "unit-1" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Owning unit" }), { target: { value: "unit-1" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Legal basis" }), { target: { value: "Synthetic" } });
    // Back keeps what was chosen.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect((screen.getByRole("combobox", { name: "File" }) as HTMLSelectElement).value).toBe("/in/ds-a/cells.csv");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    await waitFor(() => expect(onRegistered).toHaveBeenCalledWith(SOURCE));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ connection_id: "files", name: "cells.csv", location: "/in/ds-a/cells.csv",
      handling: HANDLING, legal_basis: "Synthetic", refresh: { trigger: "manual" } });  // prettier-ignore
  });

  it("does not offer a file already registered", async () => {
    serve({
      "GET /v1/ingest/connections": [],
      "GET /v1/datasets/ds-a/source-files": { root: "/in", files: [{ name: "cells.csv", source_location: "/in/ds-a/cells.csv", size_bytes: 1, modified_at: 1 }] },
    });
    render(<RegisterSourceWizard api={API} datasetId="ds-a" scheme={SCHEME} registered={["/in/ds-a/cells.csv"]} onRegistered={() => undefined} onCancel={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText(/Every file of this dataset is registered already/)).toBeTruthy();
  });
});

describe("the source page", () => {
  it("shows the profile and lineage, and says which deployed pipelines need attention after an edit", async () => {
    const calls = serve({
      "GET /v1/datasets/ds-a/sources/s1/profile": { rows_sampled: 2, sample_is_whole_source: true, values_masked: false,
        columns: [{ name: "prisoner", sample_size: 2, null_count: 0, distinct_count: 2, inferred_type: "string", type_confidence: 1 }] },
      "GET /v1/datasets/ds-a/sources/s1/lineage": [{ recipe_id: "r1", label: "Cell stays pipeline", version: 2, status: "published" }],
      "PATCH /v1/datasets/ds-a/sources/s1/governance": { source: { ...SOURCE, version: 2 }, needs_attention: ["Cell stays pipeline"] },
    });  // prettier-ignore
    const onChanged = vi.fn();
    render(<SourcePage api={API} datasetId="ds-a" source={SOURCE} scheme={SCHEME} onBack={() => undefined} onChanged={onChanged} onOpenInPipeline={() => undefined} />);
    expect(await screen.findByText("prisoner")).toBeTruthy();
    expect(await screen.findByText("Cell stays pipeline · v2 · deployed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit governance" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Classification" }), { target: { value: "SECRET" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the governance" }));
    expect(await screen.findByText(/Saved as version 2\. These deployed pipelines now need attention until deployed again: Cell stays pipeline\./)).toBeTruthy();
    const patch = calls.find((c) => c.method === "PATCH");
    expect((patch?.body as { handling: { classification: string } }).handling.classification).toBe("SECRET");
    expect(onChanged).toHaveBeenCalled();
  });
});

describe("a pipeline's source chooser", () => {
  const DRAFT = { recipe_id: "r9", version: 1, status: "draft", label: "New pipeline", owning_unit: "u", created_by: "e",
    created_at: "", ready_for_profile: false, dataset_id: "ds-a", handling: {} } as unknown as StudioRecipeDraft;  // prettier-ignore

  it("writes the chosen source's file, marking and legal basis to the draft, asking for no marking", async () => {
    const calls = serve({
      "GET /v1/datasets/ds-a/sources": [SOURCE],
      "PATCH /v1/investigations/inv-1/ingest/recipes/r9": { ...DRAFT, source_location: SOURCE.location, handling: HANDLING },
    });
    const onUsed = vi.fn();
    render(<SourceChooser apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" draft={DRAFT} disabled={false} onUsed={onUsed} onOpenDraftSettings={() => undefined} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "Registered source" }), { target: { value: "s1" } });
    expect(screen.queryByRole("combobox", { name: /Classification/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Use this source" }));
    await waitFor(() => expect(onUsed).toHaveBeenCalled());
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      label: "New pipeline", connector_profile: "generic-csv", source_location: SOURCE.location, handling: HANDLING, legal_basis: "Synthetic",
    });  // prettier-ignore
  });
});
