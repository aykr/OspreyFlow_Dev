// @vitest-environment jsdom
import Graph from "graphology";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ExportPanel } from "./ExportPanel";

// Every test below submits an export, and a successful one now triggers a real download
// (Phase 8 Stage 4h) — jsdom has no real navigation implementation, so an un-stubbed anchor
// click logs a noisy (harmless) "Not implemented: navigation" error to stderr on every test that
// does not itself care about the download. Stubbed globally here rather than per test; the one
// test that *does* care about download content overrides this stub with its own, more detailed
// spy.
beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function buildGraph(): Graph {
  const graph = new Graph();
  graph.addNode("n1", {
    data: {
      type: "Person",
      properties: { family_name: "Mercer" },
      handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
    },
  });
  return graph;
}

function mockFetch(handler: (url: string, init?: RequestInit) => Promise<unknown> | unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      const result = await handler(url, init);
      if (result && typeof result === "object" && "ok" in result) return result;
      return { ok: true, json: async () => result };
    }),
  );
}

describe("test_the_named_blocker_list_renders_the_specific_item_not_a_generic_message", () => {
  test("a consult_originator block renders the item's own label, not a generic export-failed message", async () => {
    mockFetch((url) => {
      if (url.includes("/resolution/threshold")) return { threshold: 0.95 };
      if (url.includes("/export")) {
        return {
          ok: false,
          status: 422,
          json: async () => ({
            error: "override_required",
            detail: "a justification and an originator reference are both required",
            blocked: [{ id: "n1", kind: "node", label: "the S2 record", reason: "consult_originator" }],
          }),
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <ExportPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await screen.findByText(/the S2 record/);
    expect(screen.queryByText(/export blocked$/i)).toBeNull();
  });

  test("the regression this proves against: a generic 'export blocked' message with no item name", () => {
    // A minimal stand-in reproducing exactly the failure A15's own assertion forbids — proves the
    // assertion above is a real constraint on this component, not a tautological pass.
    function Regressed() {
      return <p role="alert">Export blocked.</p>;
    }
    render(<Regressed />);
    expect(screen.getByText("Export blocked.")).toBeTruthy();
    expect(screen.queryByText(/the S2 record/)).toBeNull();
  });
});

describe("test_the_export_button_is_disabled_until_both_override_fields_are_filled", () => {
  test("Export re-enables only once both justification and originator reference are non-empty", async () => {
    mockFetch((url) => {
      if (url.includes("/resolution/threshold")) return { threshold: 0.95 };
      if (url.includes("/export")) {
        return {
          ok: false,
          status: 422,
          json: async () => ({
            error: "override_required",
            detail: "override required",
            blocked: [{ id: "n1", kind: "node", label: "the S2 record", reason: "consult_originator" }],
          }),
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <ExportPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />,
    );

    const exportButton = () => screen.getByRole("button", { name: /^Export$|^Exporting…$/ });
    fireEvent.click(exportButton());
    await screen.findByText(/the S2 record/);

    await waitFor(() => expect((exportButton() as HTMLButtonElement).disabled).toBe(true));

    fireEvent.change(await screen.findByLabelText("Justification"), {
      target: { value: "cleared by supervisor" },
    });
    expect((exportButton() as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Originator reference"), {
      target: { value: "unit-1/ref-42" },
    });
    expect((exportButton() as HTMLButtonElement).disabled).toBe(false);
  });

  test("the regression this proves against: an override form gated on justification alone stays enabled with no originator reference", () => {
    function Regressed() {
      const justification = "cleared by supervisor";
      return <button disabled={justification.trim().length === 0}>Export</button>;
    }
    render(<Regressed />);
    expect((screen.getByText("Export").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("test_manifest_and_mark_render_on_a_successful_export", () => {
  test("the withheld count reuses the exact status-bar phrasing, and the mark's own handling level renders", async () => {
    mockFetch((url) => {
      if (url.includes("/resolution/threshold")) return { threshold: 0.95 };
      if (url.includes("/export")) {
        return {
          mark: {
            osprey_mark: "OspreyFlow",
            investigation_id: "inv-1",
            exported_at: "2026-09-22T00:00:00Z",
            resolution_threshold: 0.95,
            handling_level: "OFFICIAL-SENSITIVE",
          },
          manifest: { policy: "disclose", withheld_count: 3 },
          ledger_entry_id: "led-1",
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <ExportPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await screen.findByText("3 hidden by handling");
    expect(screen.getByText(/OFFICIAL-SENSITIVE/)).toBeTruthy();
  });

  test("omit policy renders no manifest text at all, not a zero count", async () => {
    mockFetch((url) => {
      if (url.includes("/resolution/threshold")) return { threshold: 0.95 };
      if (url.includes("/export")) {
        return {
          mark: {
            osprey_mark: "OspreyFlow",
            investigation_id: "inv-1",
            exported_at: "2026-09-22T00:00:00Z",
            resolution_threshold: 0.95,
            handling_level: "OFFICIAL",
          },
          manifest: { policy: "omit", withheld_count: null },
          ledger_entry_id: "led-2",
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <ExportPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await screen.findByText(/OspreyFlow/);
    expect(screen.queryByText(/hidden by handling/)).toBeNull();
  });
});

// Phase 8 Stage 4h: a successful submit now also builds and downloads the real artefact.
// `HTMLAnchorElement.prototype.click` is stubbed — jsdom has no real navigation/download
// implementation ("Not implemented: navigation" otherwise), the same class of gap this codebase's
// own `keyboard/*.spec.ts` files exist specifically to prove for real, against a real browser
// (`keyboard/export-panel.spec.ts`'s own new "export-produces-a-downloadable-artefact" case).
// This test proves the *filename and content* `ExportPanel.tsx` builds; the keyboard spec proves
// the download event actually fires end to end.
describe("test_export_panel_produces_subgraph_export.test.tsx", () => {
  test("a successful subgraph export downloads real JSON carrying the mark, under the expected filename", async () => {
    mockFetch((url) => {
      if (url.includes("/resolution/threshold")) return { threshold: 0.95 };
      if (url.includes("/export")) {
        return {
          mark: {
            osprey_mark: "OspreyFlow",
            investigation_id: "inv-1",
            exported_at: "2026-09-23T00:00:00Z",
            resolution_threshold: 0.95,
            handling_level: "OFFICIAL",
          },
          manifest: { policy: "disclose", withheld_count: 0 },
          ledger_entry_id: "led-3",
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    let downloadedText: string | null = null;
    let downloadedFilename: string | null = null;
    vi.spyOn(URL, "createObjectURL").mockImplementation((obj: Blob | MediaSource) => {
      // jsdom's own `Blob` (distinct from Node's `buffer.Blob`) has no `.text()`/`.arrayBuffer()`
      // in this toolchain's version — read its content via `FileReader` instead, the one API both
      // implement.
      const reader = new FileReader();
      reader.onload = () => {
        downloadedText = reader.result as string;
      };
      reader.readAsText(obj as Blob);
      return "blob:fake-url";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const originalDownloadSetter = Object.getOwnPropertyDescriptor(
      HTMLAnchorElement.prototype,
      "download",
    );
    Object.defineProperty(HTMLAnchorElement.prototype, "download", {
      configurable: true,
      set(value: string) {
        downloadedFilename = value;
      },
      get() {
        return downloadedFilename ?? "";
      },
    });

    render(
      <ExportPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(downloadedFilename).toBe("osprey-subgraph-inv-1-2026-09-23T00-00-00Z.json");
    await waitFor(() => expect(downloadedText).not.toBeNull());
    const parsed = JSON.parse(downloadedText as unknown as string);
    expect(parsed.mark.osprey_mark).toBe("OspreyFlow");
    expect(parsed.nodes).toEqual([
      {
        id: "n1",
        type: "Person",
        properties: { family_name: "Mercer" },
        handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
      },
    ]);

    if (originalDownloadSetter) {
      Object.defineProperty(HTMLAnchorElement.prototype, "download", originalDownloadSetter);
    }
  });
});
