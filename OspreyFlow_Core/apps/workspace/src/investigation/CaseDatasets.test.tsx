// @vitest-environment jsdom
// ADR-099 in the Glass: a new case names the data it reads, and a case's Author changes it. The
// Conduit enforces both; these prove the Glass asks for what the analyst chose, says when nothing
// was chosen, and offers the change only to the Author.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseDatasets } from "./CaseDatasets";
import { createCase } from "./cases";
import { NewCaseForm } from "./NewCaseForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DATASETS = [
  { id: "enron", name: "Enron corpus", owning_unit: "unit-1" },
  { id: "fixture-corp", name: "Fixture Corp", owning_unit: "unit-1" },
];

function serve(routes: Record<string, (init?: RequestInit) => Response>) {
  const calls: { key: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const handler = routes[key];
      if (!handler) throw new Error(`unexpected ${key}`);
      return handler(init);
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe("a new case's data", () => {
  it("names no dataset when none is ticked, so the case gets one of its own", async () => {
    const calls = serve({ "POST /v1/investigations": () => json(201, { id: "c1", name: "X" }) });
    await createCase("http://api", "t", "X");
    expect(calls[0]!.body).toEqual({ name: "X" });
  });

  it("asks for the datasets ticked, in the order ticked", async () => {
    const calls = serve({
      "GET /v1/datasets": () => json(200, DATASETS),
      "POST /v1/investigations": () => json(201, { id: "c1", name: "Both" }),
    });
    const onCreated = vi.fn();
    render(<NewCaseForm apiBaseUrl="http://api" bearerToken="t" inputLabel="Case name" onCreated={onCreated} />);
    // ADR-099 Amendment 8: the datasets show behind the "Read existing data…" choice.
    fireEvent.click(await screen.findByRole("radio", { name: /Read existing data/ }));
    fireEvent.click(await screen.findByLabelText("Fixture Corp"));
    fireEvent.click(screen.getByLabelText("Enron corpus"));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Both" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("c1"));
    expect(calls.find((c) => c.key === "POST /v1/investigations")!.body).toEqual({
      name: "Both",
      dataset_ids: ["fixture-corp", "enron"],
    });
  });

  it("says a refused dataset in words", async () => {
    serve({ "POST /v1/investigations": () => json(422, { error: "dataset_refused" }) });
    await expect(createCase("http://api", "t", "X", ["theirs"])).rejects.toThrow(
      "One of those datasets is not one this case can read.",
    );
  });
});

describe("CaseDatasets", () => {
  const reads = () => json(200, [DATASETS[1]]);

  it("shows what the case reads and offers no change to someone who is not its Author", async () => {
    serve({
      "GET /v1/investigations/c1/datasets": reads,
      "GET /v1/investigations": () => json(200, [{ id: "c1", name: "C", level: "editor", created_at: "", created_by: "" }]),
    });
    render(<CaseDatasets apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    expect(await screen.findByText("Fixture Corp · fixture-corp")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Change what this case reads" })).toBeNull());
  });

  it("lets the Author change it, and sends the datasets ticked", async () => {
    const calls = serve({
      "GET /v1/investigations/c1/datasets": reads,
      "GET /v1/investigations": () => json(200, [{ id: "c1", name: "C", level: "author", created_at: "", created_by: "" }]),
      "GET /v1/datasets": () => json(200, DATASETS),
      "PUT /v1/investigations/c1/datasets": () => json(200, DATASETS),
    });
    const onChanged = vi.fn();
    render(<CaseDatasets apiBaseUrl="http://api" bearerToken="t" investigationId="c1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Change what this case reads" }));
    fireEvent.click(await screen.findByLabelText("Enron corpus"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.find((c) => c.key === "PUT /v1/investigations/c1/datasets")!.body).toEqual({
      dataset_ids: ["fixture-corp", "enron"],
    });
  });

  it("will not save a case reading nothing", async () => {
    serve({
      "GET /v1/investigations/c1/datasets": reads,
      "GET /v1/investigations": () => json(200, [{ id: "c1", name: "C", level: "author", created_at: "", created_by: "" }]),
      "GET /v1/datasets": () => json(200, DATASETS),
    });
    render(<CaseDatasets apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Change what this case reads" }));
    fireEvent.click(await screen.findByLabelText("Fixture Corp"));
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("telling datasets apart (ADR-099 Amendments 6 and 8)", () => {
  // Names are unique within a unit (Amendment 6), so the tick list shows the name alone — a raw
  // id there read as noise to an analyst (the owner, 9 October 2026; Amendment 8). The read-only
  // "reads …" summary below keeps the id, where an administrator comparing records needs it.
  const ALIKE = [
    { id: "01K9XQ0000000000000000ABCD", name: "Enron corpus", owning_unit: "unit-1" },
    { id: "01K9XQ0000000000000000WXYZ", name: "Enron corpus (2)", owning_unit: "unit-1" },
    { id: "enron", name: "Enron seed", owning_unit: "unit-1" },
  ];

  it("labels each choice with its name alone, even names that read alike", async () => {
    serve({ "GET /v1/datasets": () => json(200, ALIKE) });
    render(<NewCaseForm apiBaseUrl="http://api" bearerToken="t" inputLabel="Case name" onCreated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("radio", { name: /Read existing data/ }));
    expect(await screen.findByLabelText("Enron corpus")).toBeTruthy();
    expect(screen.getByLabelText("Enron corpus (2)")).toBeTruthy();
    expect(screen.getByLabelText("Enron seed")).toBeTruthy();
    expect(screen.queryByText(/…0ABCD/)).toBeNull();
  });

  it("says what the case reads with each dataset's id", async () => {
    serve({
      "GET /v1/investigations/c1/datasets": () => json(200, ALIKE.slice(0, 2)),
      "GET /v1/investigations": () => json(200, [{ id: "c1", name: "C", level: "editor", created_at: "", created_by: "" }]),
    });
    render(<CaseDatasets apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    expect(await screen.findByText("Enron corpus · …0ABCD, Enron corpus (2) · …0WXYZ")).toBeTruthy();
  });
});
