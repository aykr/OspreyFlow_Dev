// @vitest-environment jsdom
//
// ADR-127 decision 5, Amendment 10 (unit B2-5b): the author names the columns that identify a row,
// in order, so a second run into the same case skips the rows it has already loaded. The control is
// in Connect beside the source declarations, and saves through the draft's own PATCH. These prove
// what the author does: the key of an existing draft is read back in its order, a column is added
// and moved and removed, a transform is chosen from the catalogue Map offers, the key is cleared,
// the server's own refusal is read as it was said, and a draft whose key was not touched sends no
// key at all (the server keeps what a PATCH leaves unsaid).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectScreen } from "./ConnectScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CATALOGUE = [
  { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
];
const TRANSFORMS = [
  { name: "datetime", arity: 1 },
  { name: "msisdn", arity: 1 },
  { name: "coordinate_pair", arity: 2 },
  { name: "address", arity: 1, parts: ["postcode", "lines"] },
];

function draft(deduplicate: unknown = undefined, version = 1) {
  return {
    recipe_id: "r1",
    version,
    status: "draft",
    label: "Carrier A",
    connector_profile: "generic-csv",
    source_location: "/exports/a.csv",
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    legal_basis: "RIPA s22",
    owning_unit: "unit-1",
    created_by: "a1",
    created_at: "2026-10-26T09:00:00Z",
    ready_for_profile: true,
    ...(deduplicate === undefined ? {} : { deduplicate }),
  };
}

interface Served {
  patches: Record<string, unknown>[];
  posts: Record<string, unknown>[];
}

/** `patchAnswer`: what the server says to the PATCH (default: the draft it was sent, saved). */
function serve(
  existing: ReturnType<typeof draft>,
  patchAnswer?: { status: number; body: unknown },
  options: { transforms?: boolean } = {},
): Served {
  const served: Served = { patches: [], posts: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = String(url).replace("http://api", "");
      const json = (status: number, body: unknown) =>
        ({ ok: status < 400, status, json: async () => body }) as Response;
      if (path === "/v1/ingest/connectors") return json(200, CATALOGUE);
      if (path === "/v1/handling-scheme") {
        return json(200, {
          name: "uk-le",
          classification: ["PUBLIC", "OFFICIAL"],
          handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
        });
      }
      if (path === "/v1/ingest/transforms") {
        if (options.transforms === false) throw new Error("no transforms");
        return json(200, TRANSFORMS);
      }
      if (path === "/v1/investigations/inv-1/ingest/source-files") return json(200, { root: "/r", files: [] });
      if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "GET") return json(200, [existing]);
      if (path === "/v1/investigations/inv-1/ingest/recipes/r1" && method === "GET") return json(200, existing);
      if (path === "/v1/investigations/inv-1/ingest/recipes/r1" && method === "PATCH") {
        const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        served.patches.push(sent);
        if (patchAnswer) return json(patchAnswer.status, patchAnswer.body);
        return json(200, { ...existing, ...sent, handling: existing.handling });
      }
      if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "POST") {
        const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        served.posts.push(sent);
        return json(201, { ...existing, ...sent, recipe_id: "r2", handling: existing.handling });
      }
      throw new Error(`unexpected request ${method} ${path}`);
    }),
  );
  return served;
}

async function open() {
  render(<ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="tok" recipeId="r1" />);
  await screen.findByRole("group", { name: /Skip rows this case has already loaded/i });
  // The transform catalogue is read after the screen is up; wait for it where a test needs it.
}

const keyList = () => screen.getByRole("list", { name: "Key columns" });
const keyOrder = () => within(keyList()).queryAllByRole("listitem").map((li) => li.getAttribute("data-column"));

async function save() {
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
}

describe("Connect: the deduplicate control", () => {
  it("reads an existing draft's key back in its own order, with its transform", async () => {
    serve(draft({ key: [{ field: "payer" }, { field: "paid_at", transform: "datetime" }, { field: "payee" }] }));
    await open();
    expect(keyOrder()).toEqual(["payer", "paid_at", "payee"]);
    await waitFor(() =>
      expect((screen.getByLabelText("Transform for paid_at") as HTMLSelectElement).value).toBe("datetime"),
    );
  });

  it("shows no key list and a plain explanation when the draft has no key", async () => {
    serve(draft());
    await open();
    expect(screen.queryByRole("list", { name: "Key columns" })).toBeNull();
    expect(screen.getByText(/A second run into the same case skips every row it has already loaded/i)).toBeTruthy();
  });

  it("adds a column, in the order added, and saves it through the PATCH as deduplicate.key", async () => {
    const served = serve(draft());
    await open();
    const box = screen.getByLabelText("Key column name");
    fireEvent.change(box, { target: { value: "payer" } });
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "payee" } });
    fireEvent.keyDown(screen.getByLabelText("Key column name"), { key: "Enter" });
    expect(keyOrder()).toEqual(["payer", "payee"]);
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "payer" }, { field: "payee" }] });
  });

  it("does not add a blank column, and says so for a repeated one instead of ignoring it", async () => {
    serve(draft({ key: [{ field: "payer" }] }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    expect(keyOrder()).toEqual(["payer"]);
    expect(screen.queryByText(/already in the key/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "  payer " } });
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    expect(keyOrder()).toEqual(["payer"]);
    expect(screen.getByRole("status").textContent).toBe("payer is already in the key");
    // The box is left as typed so the author sees what was refused, and the notice goes once the
    // author types something else.
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "payee" } });
    expect(screen.queryByText(/already in the key/)).toBeNull();
  });

  it("warns, on a new version of a published recipe, that changing the key refuses later runs", async () => {
    serve(draft({ key: [{ field: "payer" }] }, 2));
    await open();
    expect(
      screen.getByText(
        "Changing the key will refuse later runs into a case that already holds rows loaded under the old key, until those loads are reverted.",
      ),
    ).toBeTruthy();
  });

  it("does not give that warning for a first version", async () => {
    serve(draft({ key: [{ field: "payer" }] }, 1));
    await open();
    expect(screen.queryByText(/Changing the key will refuse later runs/)).toBeNull();
  });

  it("moves a column up and down, and the saved key follows the order shown", async () => {
    const served = serve(draft({ key: [{ field: "a" }, { field: "b" }, { field: "c" }] }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Move c up" }));
    expect(keyOrder()).toEqual(["a", "c", "b"]);
    fireEvent.click(screen.getByRole("button", { name: "Move a down" }));
    expect(keyOrder()).toEqual(["c", "a", "b"]);
    // The first cannot go up and the last cannot go down.
    expect((screen.getByRole("button", { name: "Move c up" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Move b down" }) as HTMLButtonElement).disabled).toBe(true);
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "c" }, { field: "a" }, { field: "b" }] });
  });

  it("removes one column and keeps the rest in order", async () => {
    const served = serve(draft({ key: [{ field: "a" }, { field: "b" }, { field: "c" }] }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Remove b from the key" }));
    expect(keyOrder()).toEqual(["a", "c"]);
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "a" }, { field: "c" }] });
  });

  it("chooses a column's transform from the catalogue Map offers, one entry per part, single-column only", async () => {
    const served = serve(draft({ key: [{ field: "paid_at" }, { field: "post" }] }));
    await open();
    const select = (await waitFor(() => {
      const el = screen.getByLabelText("Transform for paid_at") as HTMLSelectElement;
      if (el.options.length < 2) throw new Error("catalogue not read yet");
      return el;
    })) as HTMLSelectElement;
    const offered = Array.from(select.options).map((o) => o.value);
    expect(offered).toContain("datetime");
    expect(offered).toContain("address(part=postcode)");
    expect(offered).toContain("address(part=lines)");
    expect(offered).not.toContain("address");
    expect(offered).not.toContain("coordinate_pair"); // a two-column transform is not a one-column key part
    fireEvent.change(select, { target: { value: "datetime" } });
    fireEvent.change(screen.getByLabelText("Transform for post"), { target: { value: "address(part=postcode)" } });
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({
      key: [
        { field: "paid_at", transform: "datetime" },
        { field: "post", transform: "address(part=postcode)" },
      ],
    });
    // Choosing "No transform" takes it off again.
    fireEvent.change(select, { target: { value: "" } });
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(2));
    expect(served.patches[1]!.deduplicate).toEqual({
      key: [{ field: "paid_at" }, { field: "post", transform: "address(part=postcode)" }],
    });
  });

  it("round-trips a binding the control does not edit (several columns, a literal) untouched", async () => {
    const served = serve(
      draft({
        key: [
          { field: "a" },
          { fields: ["lon", "lat"], transform: "coordinate_pair" },
          { literal: "fixed" },
        ],
      }),
    );
    await open();
    const items = within(keyList()).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[1]!.textContent).toContain("lon + lat");
    expect(items[1]!.textContent).toContain("coordinate_pair");
    expect(items[2]!.textContent).toContain("fixed");
    // They can be moved and removed, but have no transform box (their columns are Map's to change).
    expect(screen.queryByLabelText(/Transform for lon/)).toBeNull();
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({
      key: [
        { field: "a" },
        { fields: ["lon", "lat"], transform: "coordinate_pair" },
        { literal: "fixed" },
      ],
    });
  });

  it("clears the key: an empty key is sent, which is how the server is told to remove it", async () => {
    const served = serve(draft({ key: [{ field: "a" }, { field: "b" }] }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Clear the key" }));
    expect(screen.queryByRole("list", { name: "Key columns" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear the key" })).toBeNull();
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [] });
  });

  it("removing the last column clears the key the same way", async () => {
    const served = serve(draft({ key: [{ field: "a" }] }));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Remove a from the key" }));
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [] });
  });

  it("sends no deduplicate at all for a draft whose key was never set and not touched", async () => {
    const served = serve(draft());
    await open();
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect("deduplicate" in served.patches[0]!).toBe(false);
  });

  it("sends the key it read back when only something else was edited", async () => {
    const served = serve(draft({ key: [{ field: "a" }] }));
    await open();
    fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), { target: { value: "Carrier A, renamed" } });
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "a" }] });
  });

  it("shows the server's refusal as it was said, and keeps the author's key on screen", async () => {
    const cause = "deduplicate names a column the source does not have: 'payeee'";
    serve(draft(), { status: 422, body: { error: "recipe_rule", problems: [cause, "a second problem"] } });
    await open();
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "payeee" } });
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    await save();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(cause);
    expect(alert.textContent).toContain("a second problem");
    expect(keyOrder()).toEqual(["payeee"]);
  });

  it("still works when the transform catalogue cannot be read: columns can be added, no transform is offered", async () => {
    const served = serve(draft({ key: [{ field: "a" }] }), undefined, { transforms: false });
    await open();
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    await save();
    await waitFor(() => expect(served.patches).toHaveLength(1));
    expect(served.patches[0]!.deduplicate).toEqual({ key: [{ field: "a" }, { field: "b" }] });
  });

  it("a new draft carries its key in the creation request", async () => {
    const served = serve(draft());
    render(<ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="tok" />);
    fireEvent.click(await screen.findByRole("button", { name: "+ New source" }));
    fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), { target: { value: "New one" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Connector" }), { target: { value: "generic-csv" } });
    fireEvent.change(screen.getByLabelText("Key column name"), { target: { value: "id" } });
    fireEvent.click(screen.getByRole("button", { name: "Add key column" }));
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(served.posts).toHaveLength(1));
    expect(served.posts[0]!.deduplicate).toEqual({ key: [{ field: "id" }] });
  });

  it("a new draft with no key sends none", async () => {
    const served = serve(draft());
    render(<ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="tok" />);
    fireEvent.click(await screen.findByRole("button", { name: "+ New source" }));
    fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), { target: { value: "New one" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Connector" }), { target: { value: "generic-csv" } });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(served.posts).toHaveLength(1));
    expect("deduplicate" in served.posts[0]!).toBe(false);
  });
});
