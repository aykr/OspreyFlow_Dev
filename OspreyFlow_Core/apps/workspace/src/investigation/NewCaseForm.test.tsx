// @vitest-environment jsdom
//
// ADR-099 Amendment 12 item 6 (R16; Amendment 8 withdrawn): a new case reads exactly one dataset,
// chosen as "Use an existing dataset…" (one radio among the unit's datasets) or "Make a new
// dataset" (named in the form; the default). There is no third choice: the Conduit no longer gives a
// case a dataset of its own, so every create names one or the other.
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
  it("leads with the choice, Make a new dataset the default, and the datasets hidden", async () => {
    serve();
    mount();
    const fresh = (await screen.findByRole("radio", { name: /Make a new dataset/ })) as HTMLInputElement;
    expect(fresh.checked).toBe(true);
    expect(screen.getByRole("radio", { name: /Use an existing dataset/ })).toBeTruthy();
    expect(screen.getByLabelText("Name of the new dataset")).toBeTruthy();
    expect(screen.queryByRole("radio", { name: "Enron corpus" })).toBeNull();
  });

  it("makes a new dataset named in the form, or after the case when left empty", async () => {
    const fetchMock = serve();
    mount();
    await screen.findByRole("radio", { name: /Make a new dataset/ });
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() =>
      expect(sentBody(fetchMock)).toEqual({ name: "Op Example", new_dataset_name: "Op Example", domains: [] }),
    );
  });

  it("sends the new dataset's own name when one is given", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.change(await screen.findByLabelText("Name of the new dataset"), { target: { value: "Carrier C" } });
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentBody(fetchMock).new_dataset_name).toBe("Carrier C"));
    expect(sentDatasets(fetchMock)).toBeUndefined();
  });

  it("Use an existing dataset offers one choice among the datasets, named without raw ids", async () => {
    serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Use an existing dataset/ }));
    expect(await screen.findByRole("radio", { name: "Carrier B intake" })).toBeTruthy();
    expect(screen.queryByText(/5D5GG/)).toBeNull();
    // Nothing chosen yet: the case cannot be made.
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    expect((screen.getByRole("button", { name: "Create case" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("switching back to Make a new dataset forgets the chosen dataset", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Use an existing dataset/ }));
    fireEvent.click(await screen.findByRole("radio", { name: "Enron corpus" }));
    fireEvent.click(screen.getByRole("radio", { name: /Make a new dataset/ }));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentBody(fetchMock).new_dataset_name).toBe("Op Example"));
    expect(sentDatasets(fetchMock)).toBeUndefined();
  });

  it("creates over the one dataset chosen", async () => {
    const fetchMock = serve();
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: /Use an existing dataset/ }));
    fireEvent.click(await screen.findByRole("radio", { name: "Enron corpus" }));
    fireEvent.change(screen.getByLabelText("Case name"), { target: { value: "Op Example" } });
    fireEvent.click(screen.getByRole("button", { name: "Create case" }));
    await vi.waitFor(() => expect(sentDatasets(fetchMock)).toEqual(["enron"]));
    expect(sentBody(fetchMock).new_dataset_name).toBeUndefined();
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
    await screen.findByRole("radio", { name: /Make a new dataset/ });
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
