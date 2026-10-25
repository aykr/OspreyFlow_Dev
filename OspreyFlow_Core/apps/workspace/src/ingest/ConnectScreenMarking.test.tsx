// @vitest-environment jsdom
//
// Connect's classification is optional and a blank one is recorded as PUBLIC (ADR-068; owner
// rulings of 3 October 2026), and the connectors with nothing behind them are greyed *with a reason*
// ("Keep them, but say why"). The server makes the blank true; these prove the screen says it and
// does not stop the analyst saving.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectScreen } from "./ConnectScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CATALOGUE = [
  { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
  { id: "pdf", label: "PDF document", group: "Documents", structured: false, available: false },
];

function stub(classification: string[] = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"], catalogue = CATALOGUE) {
  const posts: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = url.replace("http://api", "");
      let body: unknown;
      let status = 200;
      if (path === "/v1/ingest/connectors") body = catalogue;
      else if (path === "/v1/handling-scheme") {
        body = {
          name: "uk-le",
          classification,
          handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
        };
      } else if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "GET") body = [];
      else if (path === "/v1/investigations/inv-1/ingest/source-files") body = { root: "/r", files: [] };
      else if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "POST") {
        const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        posts.push({ url: path, body: sent });
        status = 201;
        body = {
          recipe_id: "r1", version: 1, status: "draft", label: sent.label, connector_profile: sent.connector_profile,
          source_location: null, handling: { classification: "PUBLIC" }, legal_basis: null, owning_unit: "u",
          created_by: "a", created_at: "2026-10-03T00:00:00Z", ready_for_profile: false,
        };
      } else throw new Error(`unexpected request ${method} ${path}`);
      return { ok: status < 300, status, json: async () => body };
    }),
  );
  return { posts };
}

async function open() {
  render(<ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="tok" />);
  await screen.findByRole("button", { name: "Choose file…" });
}

const classificationBox = () =>
  screen.getByRole("combobox", { name: "Classification" }) as HTMLSelectElement;

describe("Connect: classification is optional and blank means PUBLIC", () => {
  it("lists PUBLIC among the classifications the scheme offers", async () => {
    stub();
    await open();
    const options = Array.from(classificationBox().options).map((o) => o.value);
    expect(options).toContain("PUBLIC");
  });

  it("starts blank, and the blank choice can be chosen again (it is not a disabled placeholder)", async () => {
    stub();
    await open();
    const box = classificationBox();
    expect(box.value).toBe("");
    const blank = Array.from(box.options).find((o) => o.value === "")!;
    expect(blank.disabled).toBe(false);
    fireEvent.change(box, { target: { value: "SECRET" } });
    fireEvent.change(box, { target: { value: "" } });
    expect(box.value).toBe("");
  });

  it("says beside the box what a blank classification becomes, and stops saying it once one is chosen", async () => {
    stub();
    await open();
    expect(screen.getByText("Left blank: recorded as PUBLIC")).toBeTruthy();
    fireEvent.change(classificationBox(), { target: { value: "OFFICIAL" } });
    expect(screen.queryByText("Left blank: recorded as PUBLIC")).toBeNull();
    fireEvent.change(classificationBox(), { target: { value: "" } });
    expect(screen.getByText("Left blank: recorded as PUBLIC")).toBeTruthy();
  });

  it("names the scheme's lowest level when the scheme has no PUBLIC", async () => {
    stub(["UNCLASSIFIED", "RESTRICTED"]);
    await open();
    expect(screen.getByText("Left blank: recorded as UNCLASSIFIED")).toBeTruthy();
  });

  it("lets a draft be saved with no classification, and sends none (the server records PUBLIC)", async () => {
    const { posts } = stub();
    await open();
    fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), {
      target: { value: "Carrier A" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Connector" }), {
      target: { value: "generic-csv" },
    });
    const create = screen.getByRole("button", { name: "Create draft" }) as HTMLButtonElement;
    expect(create.disabled).toBe(false);
    fireEvent.click(create);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect((posts[0]!.body.handling as Record<string, string>).classification).toBeUndefined();
  });
});

describe("Connect: connectors with nothing behind them say why they are greyed", () => {
  it("explains the greyed formats under the connector box", async () => {
    stub();
    await open();
    expect(screen.getByText("Greyed formats have no connector built yet.")).toBeTruthy();
  });

  it("still shows each greyed format, disabled, labelled not yet available", async () => {
    stub();
    await open();
    const pdf = screen.getByRole("option", { name: /PDF document/ }) as HTMLOptionElement;
    expect(pdf.disabled).toBe(true);
    expect(pdf.textContent).toContain("not yet available");
  });

  it("does not show the explanation when every connector is available", async () => {
    stub(undefined, [CATALOGUE[0]!]);
    await open();
    expect(screen.queryByText("Greyed formats have no connector built yet.")).toBeNull();
  });
});

// ADR-127 decision 3, Amendment 2 (B2-2b): Connect declares, beside the marking, the units a
// source's rows may name and the column that carries each part of a marking. They are saved into
// the draft's handling exactly as the API takes them (`units`, `handling_columns`), and the server's
// own 422 cause is shown as it gave it.
const UNITS_RULE =
  "handling_columns declares a column for originator but the source lists no units: a cell may name " +
  "only a unit the source declares in units";

function stubDeclarations(
  options: { draft?: Record<string, unknown>; patchFailure?: { status: number; body: unknown } } = {},
) {
  const sent: { method: string; body: Record<string, unknown> }[] = [];
  const echo = (body: Record<string, unknown>) => ({
    recipe_id: "r1", version: 1, status: "draft", label: body.label, connector_profile: body.connector_profile,
    source_location: null, handling: body.handling, legal_basis: null, owning_unit: "u",
    created_by: "a", created_at: "2026-10-25T00:00:00Z", ready_for_profile: false,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = url.replace("http://api", "");
      let body: unknown;
      let status = 200;
      if (path === "/v1/ingest/connectors") body = CATALOGUE;
      else if (path === "/v1/handling-scheme") {
        body = { name: "uk-le", classification: ["PUBLIC", "OFFICIAL", "SECRET"], handling_codes: {} };
      } else if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "GET") {
        body = options.draft ? [options.draft] : [];
      } else if (path === "/v1/investigations/inv-1/ingest/source-files") body = { root: "/r", files: [] };
      else if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "POST") {
        const request = JSON.parse(String(init?.body)) as Record<string, unknown>;
        sent.push({ method, body: request });
        status = 201;
        body = echo(request);
      } else if (path === "/v1/investigations/inv-1/ingest/recipes/r1" && method === "PATCH") {
        const request = JSON.parse(String(init?.body)) as Record<string, unknown>;
        sent.push({ method, body: request });
        if (options.patchFailure) {
          status = options.patchFailure.status;
          body = options.patchFailure.body;
        } else body = echo(request);
      } else throw new Error(`unexpected request ${method} ${path}`);
      return { ok: status < 300, status, json: async () => body };
    }),
  );
  return { sent };
}

const SAVED_DRAFT = {
  recipe_id: "r1", version: 1, status: "draft", label: "Carrier A", connector_profile: "generic-csv",
  source_location: "s3://ingest/a.csv",
  handling: {
    classification: "OFFICIAL",
    units: ["unit-1", "unit-2"],
    handling_columns: { classification: "marking", owning_unit: "unit_col" },
  },
  legal_basis: "RIPA s22", owning_unit: "u", created_by: "a", created_at: "2026-10-25T00:00:00Z",
  ready_for_profile: true,
};

async function openDeclarations(props: { recipeId?: string } = {}) {
  render(<ConnectScreen investigationId="inv-1" apiBaseUrl="http://api" bearerToken="tok" {...props} />);
  await screen.findByRole("button", { name: "Choose file…" });
}

function nameTheDraft() {
  fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), { target: { value: "Carrier A" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Connector" }), { target: { value: "generic-csv" } });
}

const unitBox = () => screen.getByRole("textbox", { name: "Unit name" }) as HTMLInputElement;
const columnBox = (part: string) => screen.getByLabelText(`Column carrying ${part}`) as HTMLInputElement;
const save = () => screen.getByRole("button", { name: /^(Create draft|Save)$/ }) as HTMLButtonElement;

describe("Connect: the units a source's rows may name", () => {
  it("adds a unit, trimmed, and sends it with the marking", async () => {
    const { sent } = stubDeclarations();
    await openDeclarations();
    nameTheDraft();
    fireEvent.change(unitBox(), { target: { value: "  unit-7  " } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    expect(screen.getByText("unit-7")).toBeTruthy();
    expect(unitBox().value).toBe("");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    expect((sent[0]!.body.handling as Record<string, unknown>).units).toEqual(["unit-7"]);
  });

  it("adds a unit on Enter, so the keyboard alone can fill the list", async () => {
    stubDeclarations();
    await openDeclarations();
    fireEvent.change(unitBox(), { target: { value: "unit-8" } });
    fireEvent.keyDown(unitBox(), { key: "Enter" });
    expect(screen.getByText("unit-8")).toBeTruthy();
  });

  it("does not add a blank name or one already listed", async () => {
    stubDeclarations();
    await openDeclarations();
    fireEvent.change(unitBox(), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    fireEvent.change(unitBox(), { target: { value: "unit-8" } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    fireEvent.change(unitBox(), { target: { value: " unit-8 " } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    expect(screen.getAllByText("unit-8")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^Remove unit / })).toHaveLength(1);
  });

  it("removes a unit", async () => {
    stubDeclarations();
    await openDeclarations();
    fireEvent.change(unitBox(), { target: { value: "unit-8" } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove unit unit-8" }));
    expect(screen.queryByText("unit-8")).toBeNull();
  });

  it("sends neither declaration for a draft that makes none (the handling stays as it was)", async () => {
    const { sent } = stubDeclarations();
    await openDeclarations();
    nameTheDraft();
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]!.body.handling).toEqual({});
  });
});

describe("Connect: the columns that carry the marking", () => {
  it("offers a text field for each of the six parts", async () => {
    stubDeclarations();
    await openDeclarations();
    for (const part of [
      "Classification", "Handling code", "Action code", "Sanitisation code", "Originator", "Owning unit",
    ]) {
      expect(columnBox(part).tagName).toBe("INPUT");
    }
  });

  it("sends a declared column trimmed, and leaves a blank one undeclared", async () => {
    const { sent } = stubDeclarations();
    await openDeclarations();
    nameTheDraft();
    fireEvent.change(columnBox("Classification"), { target: { value: "  marking  " } });
    fireEvent.change(columnBox("Handling code"), { target: { value: "   " } });
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    expect((sent[0]!.body.handling as Record<string, unknown>).handling_columns).toEqual({
      classification: "marking",
    });
  });

  it("refuses an originator or owning-unit column with no unit, in the server's own words, until a unit is added", async () => {
    stubDeclarations();
    await openDeclarations();
    nameTheDraft();
    fireEvent.change(columnBox("Originator"), { target: { value: "origin" } });
    expect(screen.getByText(UNITS_RULE)).toBeTruthy();
    expect(save().disabled).toBe(true);
    fireEvent.change(unitBox(), { target: { value: "unit-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
    expect(screen.queryByText(UNITS_RULE)).toBeNull();
    expect(save().disabled).toBe(false);
  });

  it("names both parts when both unit columns are declared", async () => {
    stubDeclarations();
    await openDeclarations();
    fireEvent.change(columnBox("Originator"), { target: { value: "origin" } });
    fireEvent.change(columnBox("Owning unit"), { target: { value: "owner" } });
    expect(screen.getByText(UNITS_RULE.replace("for originator", "for originator and owning_unit"))).toBeTruthy();
  });

  it("does not ask for units when the declared columns carry no unit", async () => {
    stubDeclarations();
    await openDeclarations();
    nameTheDraft();
    fireEvent.change(columnBox("Classification"), { target: { value: "marking" } });
    expect(screen.queryByText(/lists no units/)).toBeNull();
    expect(save().disabled).toBe(false);
  });
});

describe("Connect: a draft's declarations round-trip", () => {
  it("loads an existing draft's units and columns into the form", async () => {
    stubDeclarations({ draft: SAVED_DRAFT });
    await openDeclarations({ recipeId: "r1" });
    await waitFor(() => expect(screen.getByText("unit-1")).toBeTruthy());
    expect(screen.getByText("unit-2")).toBeTruthy();
    expect(columnBox("Classification").value).toBe("marking");
    expect(columnBox("Owning unit").value).toBe("unit_col");
    expect(columnBox("Originator").value).toBe("");
  });

  it("keeps them through an edit of the marking", async () => {
    const { sent } = stubDeclarations({ draft: SAVED_DRAFT });
    await openDeclarations({ recipeId: "r1" });
    await waitFor(() => expect(screen.getByText("unit-1")).toBeTruthy());
    fireEvent.change(classificationBox(), { target: { value: "SECRET" } });
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]!.method).toBe("PATCH");
    expect(sent[0]!.body.handling).toEqual({
      classification: "SECRET",
      units: ["unit-1", "unit-2"],
      handling_columns: { classification: "marking", owning_unit: "unit_col" },
    });
  });

  it("clears them explicitly when the analyst removes every one (an absent key would keep the old)", async () => {
    const { sent } = stubDeclarations({ draft: SAVED_DRAFT });
    await openDeclarations({ recipeId: "r1" });
    await waitFor(() => expect(screen.getByText("unit-1")).toBeTruthy());
    fireEvent.change(columnBox("Owning unit"), { target: { value: "" } });
    fireEvent.change(columnBox("Classification"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove unit unit-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove unit unit-2" }));
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]!.body.handling).toEqual({ classification: "OFFICIAL", units: [], handling_columns: {} });
  });
});

describe("Connect: the server's 422 cause is shown as it gave it", () => {
  it("shows a source_declarations_invalid detail verbatim", async () => {
    const cause = "handling units must be a list of non-empty unit names";
    stubDeclarations({
      draft: SAVED_DRAFT,
      patchFailure: { status: 422, body: { error: "source_declarations_invalid", detail: cause } },
    });
    await openDeclarations({ recipeId: "r1" });
    await waitFor(() => expect(screen.getByText("unit-1")).toBeTruthy());
    fireEvent.click(save());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(cause);
  });
});
