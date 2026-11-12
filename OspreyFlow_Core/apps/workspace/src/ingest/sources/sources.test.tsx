// @vitest-environment jsdom
// ADR-140 Amendment 4 (redesign phase 3), the Glass: what would fail if each part were wrong — the
// wizard registering before its governance is complete, or sending something other than what was
// chosen; Back losing nothing; the source page's governance edit not saying which deployed pipelines
// now need attention; a pipeline's source chooser not writing the source's marking to the draft.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SourceTable, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { EMPTY_GOVERNANCE, GovernanceFields } from "./GovernanceFields";
import { RegisterSourceWizard } from "./RegisterSourceWizard";
import { SourceChooser } from "./SourceChooser";
import { SOURCE_WORDS, SourcePage } from "./SourcePage";
import { StudioRights } from "../studio/rightsGate";

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

// ADR-110 Amendments 6 and 13 (redesign phase 4): the refresh policy's mode, said in words, and its
// pause. What would fail: an incremental policy saved without its column; the mode not sent; the
// page not saying whom a refresh runs as or why it is paused; a pause or resume not reaching its route.
describe("the source page's refresh", () => {
  const PAGE_ROUTES = {
    "GET /v1/datasets/ds-a/sources/s1/profile": { rows_sampled: 0, sample_is_whole_source: true, values_masked: false, columns: [] },
    "GET /v1/datasets/ds-a/sources/s1/lineage": [],
  };  // prettier-ignore
  const WATCHED: SourceTable = {
    ...SOURCE,
    refresh: { trigger: "watch", pattern: "cells-*.csv", mode: "snapshot", dropped_rows: "withdraw", owner: "eng-1", paused: false },
  };

  it("says how each file is read, whom it runs as, and that it is running", async () => {
    serve(PAGE_ROUTES);
    render(<SourcePage api={API} datasetId="ds-a" source={WATCHED} scheme={SCHEME} onBack={() => undefined} onChanged={() => undefined} onOpenInPipeline={() => undefined} />);
    expect(
      await screen.findByText(
        "when a file matching cells-*.csv arrives, reading the whole file and withdrawing the events of rows it no longer carries; their nodes and links stay until their load is reverted",
      ),
    ).toBeTruthy();
    expect(screen.getByText("eng-1")).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();
  });

  it("refuses an incremental refresh without its watermark column, and sends the mode chosen", async () => {
    const calls = serve({
      ...PAGE_ROUTES,
      "PATCH /v1/datasets/ds-a/sources/s1/governance": { source: { ...WATCHED, version: 2 }, needs_attention: [] },
    });
    render(<SourcePage api={API} datasetId="ds-a" source={WATCHED} scheme={SCHEME} onBack={() => undefined} onChanged={() => undefined} onOpenInPipeline={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit governance" }));
    fireEvent.change(screen.getByRole("combobox", { name: "How each file is read" }), { target: { value: "incremental" } });
    expect(screen.queryByRole("combobox", { name: "Rows a new file no longer carries" })).toBeNull();
    expect(screen.getByText(/Still to give: a watermark column/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the governance" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Watermark column (its values only grow)" }), { target: { value: "booked_at" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the governance" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const sent = calls.find((c) => c.method === "PATCH")?.body as { refresh: { mode: string; watermark_column: string } };
    expect([sent.refresh.mode, sent.refresh.watermark_column]).toEqual(["incremental", "booked_at"]);
  });

  it("pauses with the reason given, says so, and resumes", async () => {
    const pausedSource = { ...WATCHED, refresh: { ...WATCHED.refresh, paused: true, paused_reason: "waiting for the visits step" } };
    const calls = serve({
      ...PAGE_ROUTES,
      "POST /v1/datasets/ds-a/sources/s1/refresh/pause": pausedSource,
      "POST /v1/datasets/ds-a/sources/s1/refresh/resume": WATCHED,
    });
    const onChanged = vi.fn();
    const { rerender } = render(
      <SourcePage api={API} datasetId="ds-a" source={WATCHED} scheme={SCHEME} onBack={() => undefined} onChanged={onChanged} onOpenInPipeline={() => undefined} />,
    );
    fireEvent.change(await screen.findByRole("textbox", { name: "Why pause it (optional)" }), { target: { value: "waiting for the visits step" } });
    fireEvent.click(screen.getByRole("button", { name: "Pause the refresh" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(pausedSource));
    expect(calls.find((c) => c.path.endsWith("/refresh/pause"))?.body).toEqual({ reason: "waiting for the visits step" });
    rerender(<SourcePage api={API} datasetId="ds-a" source={pausedSource} scheme={SCHEME} onBack={() => undefined} onChanged={onChanged} onOpenInPipeline={() => undefined} />);
    expect(screen.getByText("paused: waiting for the visits step")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Resume the refresh" }));
    await waitFor(() => expect(onChanged).toHaveBeenLastCalledWith(WATCHED));
    expect(screen.getByRole("status").textContent).toBe("The refresh is resumed.");
  });

  it("offers no pause for a source refreshed by hand", async () => {
    serve(PAGE_ROUTES);
    render(<SourcePage api={API} datasetId="ds-a" source={SOURCE} scheme={SCHEME} onBack={() => undefined} onChanged={() => undefined} onOpenInPipeline={() => undefined} />);
    expect(await screen.findByText("by hand")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Pause the refresh" })).toBeNull();
  });
});

// ADR-140 Amendment 19: a source's declared default marking, which an unmarked table's rows carry
// before a join. What would fail: the page not saying none is declared and what that means; the
// choice not reaching its route; who declared it and when not said; a person without Deploy
// pipelines offered the save; a refusal shown as a status code.
describe("the source page's default marking", () => {
  const PAGE_ROUTES = {
    "GET /v1/datasets/ds-a/sources/s1/profile": { rows_sampled: 0, sample_is_whole_source: true, values_masked: false, columns: [] },
    "GET /v1/datasets/ds-a/sources/s1/lineage": [],
  };  // prettier-ignore
  const page = (source: SourceTable, rights: ReadonlySet<string> | null = null) =>
    render(
      <StudioRights.Provider value={rights}>
        <SourcePage api={API} datasetId="ds-a" source={source} scheme={SCHEME} onBack={() => undefined} onChanged={() => undefined} onOpenInPipeline={() => undefined} />
      </StudioRights.Provider>,
    );

  it("says none is declared, and that the table is then never joined to a marked one", async () => {
    serve(PAGE_ROUTES);
    page(SOURCE);
    expect(await screen.findByText(SOURCE_WORDS.noDefault)).toBeTruthy();
  });

  it("sends the chosen marking, then says who declared it and when, and which pipelines need attention", async () => {
    const declared = { ...SOURCE, version: 2, default_marking: "OFFICIAL", default_marking_set_by: "eng-1", default_marking_set_at: "2026-11-12T10:00:00Z" };
    const calls = serve({ ...PAGE_ROUTES, "PUT /v1/datasets/ds-a/sources/s1/default-marking": { source: declared, needs_attention: ["Cell stays pipeline"] } });  // prettier-ignore
    const onChanged = vi.fn();
    render(<SourcePage api={API} datasetId="ds-a" source={SOURCE} scheme={SCHEME} onBack={() => undefined} onChanged={onChanged} onOpenInPipeline={() => undefined} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "Default marking" }), { target: { value: "OFFICIAL" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the default marking" }));
    expect(await screen.findByText(/Saved as version 2\. These deployed pipelines now need attention until deployed again: Cell stays pipeline\./)).toBeTruthy();
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toEqual({ default_marking: "OFFICIAL" });
    expect(onChanged).toHaveBeenCalledWith(declared);
    cleanup();
    serve(PAGE_ROUTES);
    page(declared);
    expect(await screen.findByText("OFFICIAL, declared by eng-1 on 12 November 2026.")).toBeTruthy();
  });

  it("says a default left below the source's own marking is not carried", async () => {
    serve(PAGE_ROUTES);
    page({ ...SOURCE, handling: { ...HANDLING, classification: "SECRET" }, default_marking: "OFFICIAL",
      default_marking_set_by: "eng-1", default_marking_set_at: "2026-11-12T10:00:00Z" });  // prettier-ignore
    expect(await screen.findByText(SOURCE_WORDS.belowOwn)).toBeTruthy();
  });

  it("clears a declared default by choosing None", async () => {
    const declared = { ...SOURCE, default_marking: "OFFICIAL", default_marking_set_by: "eng-1", default_marking_set_at: "2026-11-12T10:00:00Z" };
    const calls = serve({ ...PAGE_ROUTES, "PUT /v1/datasets/ds-a/sources/s1/default-marking": { source: { ...SOURCE, version: 3 }, needs_attention: [] } });  // prettier-ignore
    page(declared);
    const choice = (await screen.findByRole("combobox", { name: "Default marking" })) as HTMLSelectElement;
    expect(choice.value).toBe("OFFICIAL");
    fireEvent.change(choice, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the default marking" }));
    expect(await screen.findByText("Saved as version 3.")).toBeTruthy();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ default_marking: null });
  });

  it("offers the save only with Deploy pipelines, saying who can", async () => {
    const calls = serve(PAGE_ROUTES);
    page(SOURCE, new Set(["add_ingest_files", "edit_pipelines"]));
    const save = await screen.findByRole("button", { name: "Save the default marking" });
    expect(save.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(save);
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("shows a refusal in its own words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = new URL(String(url)).pathname;
        if (init?.method === "PUT")
          return { ok: false, status: 422, json: async () => ({ error: "default_marking_refused", problems: ["the default marking is above your clearance"] }) } as Response;  // prettier-ignore
        const found = (PAGE_ROUTES as Record<string, unknown>)[`GET ${path}`];
        return { ok: true, status: 200, json: async () => found } as Response;
      }),
    );
    page(SOURCE);
    fireEvent.change(await screen.findByRole("combobox", { name: "Default marking" }), { target: { value: "SECRET" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the default marking" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("above your clearance"));
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

describe("a full snapshot's dropped rows, in words (ADR-110 Amendment 15)", () => {
  it("offers to withdraw only their events, and says their nodes and links stay", () => {
    const value = {
      ...EMPTY_GOVERNANCE,
      refresh: { trigger: "watch" as const, pattern: "cells-*.csv", mode: "snapshot" as const, dropped_rows: "keep" as const, owner: "eng-1", paused: false },
    };
    render(<GovernanceFields scheme={SCHEME} value={value} onChange={() => undefined} />);
    expect(screen.getByRole("option", { name: "Keep them and their events" })).toBeTruthy();
    expect(
      screen.getByRole("option", {
        name: "Withdraw their events; their nodes and links stay until their load is reverted (reverting the refresh restores the events)",
      }),
    ).toBeTruthy();
  });
});
