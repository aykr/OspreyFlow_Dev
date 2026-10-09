// @vitest-environment jsdom
//
// ADR-099 Amendment 8 (owner, 9 October 2026): what a new case can see is a first-class choice —
// "Start empty" (the default) or "Read existing data…", which reveals the datasets. The old form
// led with a bare tick list whose purpose was explained only in fine print at the bottom.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.queryByRole("checkbox")).toBeNull();
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
});
