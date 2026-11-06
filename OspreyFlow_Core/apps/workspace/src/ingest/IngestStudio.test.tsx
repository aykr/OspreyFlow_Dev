// @vitest-environment jsdom
// ADR-140 decision 1 (redesign phase 2): the Studio reads as four places — 1 Model, 2 Sources,
// 3 Pipelines, 4 Runs — under a readiness strip, opened on a dataset. Each case below is the test
// that fails if that part goes: the four tabs, the strip's figures, the switcher choosing the case
// that loads into the chosen dataset (never one that only reads it), and Sources keeping the
// unstructured path (ADR-094 step 3) that was the Files tab.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngestStudio } from "./IngestStudio";

vi.mock("./map/MapScreen", () => ({ MapScreen: () => null }));
vi.mock("./verify/VerifyScreen", () => ({ VerifyScreen: () => null }));
vi.mock("./publish/PublishScreen", () => ({ PublishScreen: () => null }));
vi.mock("./ProfileScreen", () => ({ ProfileScreen: () => null }));
vi.mock("./ConnectScreen", () => ({ ConnectScreen: () => null }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CASES = [
  { id: "inv-1", name: "PID case", level: "editor", created_at: "", created_by: "e", domains: ["niem"],
    datasets: ["Prison Intelligence Dataset"], dataset_ids: ["prison-intelligence"] },
  { id: "inv-2", name: "Carrier B intake", level: "author", created_at: "", created_by: "e",
    datasets: ["Carrier B", "HMP extract"], dataset_ids: ["carrier-b", "hmp"] },
];  // prettier-ignore

const REGISTRY = [
  { recipe_id: "r1", version: 1, status: "published", label: "PIN calls", source_location: "/ingest/pin.csv",
    handling: { classification: "OFFICIAL" }, legal_basis: "Prison Act", owning_unit: "u", created_by: "e",
    created_at: "", ready_for_profile: true },
  { recipe_id: "r2", version: 4, status: "draft", label: "Intel reports", source_location: "/ingest/reports.csv",
    owning_unit: "u", created_by: "e", created_at: "", ready_for_profile: false },
];  // prettier-ignore

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      const json = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;
      if (path.endsWith("/v1/investigations")) return json(CASES);
      if (path.endsWith("/ingest/recipe-registry")) return json(REGISTRY);
      if (path.endsWith("/ingest/recipes/r1/runs"))
        return json([{ run_id: "x", trigger: "manual", started_at: "2026-11-05T18:39:00Z", outcome: "succeeded", run_as: "e" }]);
      return json([]);
    }),
  );
}

function open(onOpenCase = vi.fn()) {
  render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" onOpenCase={onOpenCase} />);
  return onOpenCase;
}

describe("IngestStudio: four places", () => {
  it("offers 1 Model, 2 Sources, 3 Pipelines and 4 Runs, Pipelines first", () => {
    serve();
    open();
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["1 Model", "2 Sources", "3 Pipelines", "4 Runs"]);
    expect(screen.getByRole("tab", { name: "3 Pipelines" }).getAttribute("aria-selected")).toBe("true");
  });

  it("says where the dataset stands: model, sources, pipelines with untested drafts, last run", async () => {
    serve();
    open();
    const strip = screen.getByRole("list", { name: "Where this dataset stands" });
    expect(await within(strip).findByText(/last run 5 Nov 2026, \d\d:\d\d, succeeded/)).toBeTruthy();
    expect(within(strip).getByText("Model: POLE core + Crime case analysis (NIEM)")).toBeTruthy();
    expect(within(strip).getByText("2 sources")).toBeTruthy();
    expect(within(strip).getByText("2 pipelines · 1 untested")).toBeTruthy();
  });

  it("switches dataset through the case that loads into it, and offers no dataset a case only reads", async () => {
    serve();
    const onOpenCase = open();
    const switcher = await screen.findByRole("combobox", { name: "Dataset" });
    await screen.findByRole("option", { name: "Carrier B" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Prison Intelligence Dataset", "Carrier B"]);
    fireEvent.change(switcher, { target: { value: "carrier-b" } });
    expect(onOpenCase).toHaveBeenCalledWith("inv-2");
  });

  it("shows the target model on Model, and the sources with their marking on Sources", async () => {
    serve();
    open();
    fireEvent.click(screen.getByRole("tab", { name: "1 Model" }));
    expect(await screen.findByText("POLE core + Crime case analysis (NIEM)")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "2 Sources" }));
    const sources = await screen.findByRole("region", { name: "Sources" });
    expect(await within(sources).findByText("pin.csv")).toBeTruthy();
    expect(within(sources).getByText("OFFICIAL")).toBeTruthy();
    expect(within(sources).getByText("not yet marked")).toBeTruthy();
  });

  it("keeps the files added straight to the dataset on Sources, behind Add files", async () => {
    serve();
    open();
    fireEvent.click(screen.getByRole("tab", { name: "2 Sources" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add files" }));
    expect(await screen.findByRole("region", { name: "Add files" })).toBeTruthy();
  });

  it("opens on nothing before there is a case to work through", () => {
    serve();
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId={null} onOpenCase={vi.fn()} />);
    expect(screen.queryByRole("tab")).toBeNull();
  });
});
