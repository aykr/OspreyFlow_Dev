// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import { makeEdge } from "../testing/fixtures";
import { LinkChange } from "./LinkChange";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const EDGE_TYPES: EdgeTypeDef[] = [
  { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"] },
  {
    name: "FAMILY_OF",
    from: ["Person"],
    to: ["Person"],
    properties: [{ name: "relation", type: "string", required: true }],
  },
  { name: "SAME_AS", from: ["*"], to: ["*"], system: true },
];

const edge = makeEdge("e1", "a", "b", { type: "ASSOCIATE_OF", occurrences: 3 });

function mount(onChanged = vi.fn(), openSignal = 0) {
  render(
    <LinkChange
      apiBaseUrl="http://api.test"
      bearerToken="tok"
      investigationId="inv-1"
      edge={edge}
      sourceType="Person"
      targetType="Person"
      edgeTypes={EDGE_TYPES}
      openSignal={openSignal}
      onChanged={onChanged}
    />,
  );
  return onChanged;
}

function stubFetch(status: number, json: unknown) {
  const fetchMock = vi.fn(async () => ({ ok: status === 200, status, json: async () => json }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("LinkChange", () => {
  it("is closed until asked, and opens from the link menu's signal", () => {
    mount();
    expect(screen.queryByLabelText("Link type")).toBeNull();
    cleanup();
    mount(vi.fn(), 1);
    expect(screen.getByLabelText("Link type")).toBeTruthy();
  });

  it("offers the types the two ends allow and never a same-as type", () => {
    mount(vi.fn(), 1);
    const options = Array.from(screen.getByLabelText("Link type").querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(options).toEqual(["ASSOCIATE_OF", "FAMILY_OF"]);
  });

  it("will not save without a reason", () => {
    mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Records behind it"), { target: { value: "7" } });
    const save = screen.getByRole("button", { name: "Save change" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "Seen again" } });
    expect(save.disabled).toBe(false);
  });

  it("shows the fields the chosen type records, and says which are required", () => {
    mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Link type"), { target: { value: "FAMILY_OF" } });
    expect(screen.getByLabelText(/relation \(required\)/)).toBeTruthy();
  });

  it("sends only the change with its reason and hands the result to the caller", async () => {
    const result = { edge: { ...edge, id: "e2" }, delta: { op: "replace_edge", seq: 2 }, change: { id: "c1" } };
    const fetchMock = stubFetch(200, result);
    const onChanged = mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Records behind it"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "Seen again" } });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(result));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/v1/investigations/inv-1/links/e1/change");
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Seen again", occurrences: 7 });
    expect(screen.getByRole("status").textContent).toContain("Link changed");
  });

  it("says what is wrong before asking the server, and keeps the form open", () => {
    const fetchMock = stubFetch(200, {});
    mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Link type"), { target: { value: "FAMILY_OF" } });
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "Told so" } });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    expect(screen.getByRole("alert").textContent).toBe("relation is required for FAMILY_OF.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's refusal and records nothing when the save fails", async () => {
    stubFetch(422, { error: "invalid_link_change", detail: "'FAMILY_OF' does not permit to='Organisation'" });
    const onChanged = mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Records behind it"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "r" } });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("does not permit"));
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Link type")).toBeTruthy();
  });

  it("says plainly when the save did not happen at all", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Records behind it"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "r" } });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "The link was not changed. Nothing was recorded; try again.",
      ),
    );
  });

  it("Escape closes the form and puts the link's own values back", () => {
    mount(vi.fn(), 1);
    fireEvent.change(screen.getByLabelText("Records behind it"), { target: { value: "9" } });
    fireEvent.keyDown(screen.getByLabelText("Records behind it"), { key: "Escape" });
    expect(screen.queryByLabelText("Link type")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change this link…" }));
    expect((screen.getByLabelText("Records behind it") as HTMLInputElement).value).toBe("3");
  });
});

// ADR-081 step B: the form asks what stands behind the link, with no default.
describe("LinkChange and the basis", () => {
  const BASIS_TYPES: EdgeTypeDef[] = [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "direct" },
    { name: "LIKELY_ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "probabilistic" },
  ];
  function mountWith(link: ReturnType<typeof makeEdge>, onChanged = vi.fn()) {
    render(
      <LinkChange
        apiBaseUrl="http://api.test"
        bearerToken="tok"
        investigationId="inv-1"
        edge={link}
        sourceType="Person"
        targetType="Person"
        edgeTypes={BASIS_TYPES}
        openSignal={1}
        onChanged={onChanged}
      />,
    );
    return onChanged;
  }

  it("asks with two unchecked choices for a link of a Direct type", () => {
    mountWith(edge);
    const group = screen.getByRole("radiogroup", { name: /stands behind/i });
    const radios = Array.from(group.querySelectorAll("input[type=radio]")) as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual(["direct", "probabilistic"]);
    expect(radios.every((r) => !r.checked)).toBe(true);
  });

  it("will not save until the basis is chosen, then sends the mark with the reason", async () => {
    const fetchMock = stubFetch(200, {
      edge: { ...edge, id: "e2", basis: "probabilistic" },
      delta: { seq: 2, op: "replace_edge", old_edge_id: "e1", edge: { ...edge, id: "e2" } },
      change: { id: "c1", reason: "Inferred from timing." },
    });
    mountWith(edge);
    fireEvent.change(screen.getByLabelText(/Why is it being changed/), { target: { value: "Inferred from timing." } });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/stands behind/i);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/^Probabilistic/));
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, init] = (fetchMock.mock.calls[0] as unknown as [string, RequestInit]);
    expect(JSON.parse(String(init.body))).toEqual({ reason: "Inferred from timing.", basis: "probabilistic" });
  });

  it("states the one possible basis as fixed text for a link that is already probabilistic", () => {
    mountWith(makeEdge("e9", "a", "b", { type: "LIKELY_ASSOCIATE_OF" }));
    expect(screen.queryByRole("radiogroup", { name: /stands behind/i })).toBeNull();
    expect(document.body.textContent).toMatch(/Probabilistic/);
    expect(document.body.textContent).toMatch(/only basis/i);
  });
});
