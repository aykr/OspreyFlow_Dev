// @vitest-environment jsdom
//
// ADR-099 Amendment 8 (owner, 9 October 2026): what a new case can see is a first-class choice —
// "Start empty" (the default) or "Read existing data…", which reveals the datasets. The old form
// led with a bare tick list whose purpose was explained only in fine print at the bottom.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NewCaseForm } from "./NewCaseForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(created: { id: string } = { id: "case-1" }) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/v1/datasets")) {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { id: "ds-01JEX5D5GG", name: "Carrier B intake" },
          { id: "enron", name: "Enron corpus" },
        ],
      };
    }
    return { ok: true, status: 201, json: async () => ({ ...created, init }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mount() {
  const onCreated = vi.fn();
  render(
    <NewCaseForm apiBaseUrl="http://api.test" bearerToken="tok" inputLabel="Case name" onCreated={onCreated} />,
  );
  return onCreated;
}

function sentBody(fetchMock: ReturnType<typeof serve>): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/v1/investigations"));
  if (!call) throw new Error("no create call was made");
  return JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>;
}

function sentDatasets(fetchMock: ReturnType<typeof serve>): unknown {
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/v1/investigations"));
  if (!call) throw new Error("no create call was made");
  return (JSON.parse(String((call[1] as RequestInit).body)) as { dataset_ids?: unknown }).dataset_ids;
}

describe("NewCaseForm", () => {
  it("leads with the choice, Start empty the default, and the datasets hidden", async () => {
    serve();
    mount();
    const empty = (await screen.findByRole("radio", { name: /Start empty/ })) as HTMLInputElement;
    expect(empty.checked).toBe(true);
    expect(screen.getByRole("radio", { name: /Read existing data/ })).toBeTruthy();
    // The datasets are hidden; the domain models (ADR-126) are not datasets and are always shown.
    expect(screen.queryByRole("checkbox", { name: "Enron corpus" })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Carrier B intake" })).toBeNull();
  });

  it("creates an empty case without ever showing the dataset list", async () => {
    const fetchMock = serve();
    mount();
    await screen.findByRole("radio", { name: /Start empty/ });
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    // No `dataset_ids` key at all: the Conduit then gives the case a dataset of its own.
    await vi.waitFor(() => expect(sentDatasets(fetchMock)).toBeUndefined());
  });

  it("Read existing data reveals the datasets, named without raw ids", async () => {
    serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Read existing data/ }));
    const carrier = await screen.findByRole("checkbox", { name: "Carrier B intake" });
    expect(carrier).toBeTruthy();
    expect(screen.queryByText(/5D5GG/)).toBeNull();
  });

  it("switching back to Start empty forgets the ticked datasets", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Read existing data/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Enron corpus" }));
    fireEvent.click(screen.getByRole("radio", { name: /Start empty/ }));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentDatasets(fetchMock)).toBeUndefined());
  });

  it("creates with the ticked datasets when reading existing data", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Read existing data/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Enron corpus" }));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentDatasets(fetchMock)).toEqual(["enron"]));
  });

  // ADR-126 decision 1: the case's domain packs are chosen when it is made.
  it("offers the three domain models by the Studio's labels, none ticked, and says POLE", async () => {
    serve();
    mount();
    const group = await screen.findByRole("group", { name: "Domain models" });
    const boxes = within(group).getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes.map((b) => b.parentElement?.textContent)).toEqual([
      "Financial fraud and AML (FIBO)",
      "Crime case analysis (NIEM)",
      "Cyber threat analytics (STIX 2.1)",
    ]);
    expect(boxes.every((b) => !b.checked)).toBe(true);
    expect(within(group).getByText("Bespoke POLE (the core model)")).toBeTruthy();
  });

  it("stops saying POLE once a domain model is ticked", async () => {
    serve();
    mount();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Crime case analysis (NIEM)" }));
    expect(screen.queryByText("Bespoke POLE (the core model)")).toBeNull();
  });

  it("sends domains: [] when none is ticked, so the case counts as chosen POLE", async () => {
    const fetchMock = serve();
    mount();
    await screen.findByRole("radio", { name: /Start empty/ });
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentBody(fetchMock).domains).toEqual([]));
  });

  it("sends the domain models ticked, in the catalogue's order whatever the order ticked", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Crime case analysis (NIEM)" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Financial fraud and AML (FIBO)" }));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentBody(fetchMock).domains).toEqual(["fibo", "niem"]));
  });
});
