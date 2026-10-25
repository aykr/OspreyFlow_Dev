// @vitest-environment jsdom
//
// ADR-127 decision 3, Amendment 2 (B2-2b): an element's handling part is the source's default, a
// literal value, or `{field: <column>}` read per row from the column Connect declared for it. The
// editor once read every part as a string (`override?.classification as string`), which a binding
// object is not; and every declared part must be bound on every element, a reference included.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RecipeEdge, RecipeEntity } from "../../../../../packages/schemas/generated";
import type { HandlingScheme } from "../api";
import { ElementInspector } from "./ElementInspector";

afterEach(cleanup);

const ONTOLOGY = {
  version: 12,
  entity_types: [{ name: "Endpoint", pole_class: "object", channel: "cyan", shape: "circle", properties: [] }],
  edge_types: [{ name: "OWNS", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" }],
} as unknown as OntologySchema;

const SCHEME: HandlingScheme = {
  name: "uk-le",
  classification: ["PUBLIC", "OFFICIAL", "SECRET"],
  handling_codes: {
    P: { label: "Permissive", dissemination: "permitted" },
    C: { label: "Conditional", dissemination: "conditional" },
    R: { label: "Restricted", dissemination: "restricted" },
  },
  action_codes: {
    A1: { label: "Act freely", direct_action: true },
    A2: { label: "Do not act directly", direct_action: false },
    A3: { label: "Ask the originator first", direct_action: false, originator_permission: true },
  },
  sanitisation_codes: {
    S1: { label: "Sanitised", consult_originator: false },
    S2: { label: "Consult the originator", consult_originator: true },
  },
};

const COLUMNS = ["marking", "code", "caveat", "san", "origin", "owner", "other"];

const ALL_DECLARED = {
  classification: "marking",
  handling_code: "code",
  action_code: "caveat",
  sanitisation_code: "san",
  originator: "origin",
  owning_unit: "owner",
};

const LABELS: Record<string, string> = {
  classification: "Classification",
  handling_code: "Handling code",
  action_code: "Action code",
  sanitisation_code: "Sanitisation code",
  originator: "Originator",
  owning_unit: "Owning unit",
};

function entityOf(handling: Record<string, unknown> | null, extra: Partial<RecipeEntity> = {}): RecipeEntity {
  return { ref: "e1", pole_class: "object", type: "Endpoint", on_match: "create", properties: {}, handling, ...extra } as RecipeEntity;
}

function mount(
  entity: RecipeEntity,
  declaredColumns: Record<string, string> | undefined,
  onChangeEntity = vi.fn(),
  onPreviewHandling = vi.fn(),
  sourceHandling: Record<string, unknown> = {},
) {
  render(
    <ElementInspector
      selection={{ kind: "entity", entity }}
      ontology={ONTOLOGY}
      transforms={[]}
      sourceFieldNames={COLUMNS}
      baselineClassification="OFFICIAL"
      classificationOrder={SCHEME.classification}
      handlingScheme={SCHEME}
      sourceHandling={sourceHandling}
      declaredColumns={declaredColumns}
      onChangeEntity={onChangeEntity}
      onChangeEdge={vi.fn()}
      onDelete={vi.fn()}
      onPreviewHandling={onPreviewHandling}
    />,
  );
  return { onChangeEntity, onPreviewHandling };
}

const partBox = (part: string) => screen.getByLabelText(`${LABELS[part]} for this element`) as HTMLSelectElement;
const fromColumn = (part: string) =>
  Array.from(partBox(part).options).find((o) => o.value === "__column__") as HTMLOptionElement;

describe("ElementInspector: a handling part bound to a column is not read as a string", () => {
  it("shows a bound classification as From column, not as a miscast value", () => {
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking" });
    expect(partBox("classification").value).toBe("__column__");
    expect(screen.queryByText(/object Object/)).toBeNull();
  });

  it("does not call a binding a loosening of the source's marking", () => {
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking" });
    expect(screen.queryByText(/loosens the source/)).toBeNull();
  });

  it("still calls a literal classification below the source's a loosening", () => {
    mount(entityOf({ classification: "PUBLIC" }), {});
    expect(screen.getByText(/loosens the source/)).toBeTruthy();
  });

  it("sends the binding to the preview untouched", async () => {
    const onPreviewHandling = vi.fn(async () => ({
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      provenance: { state: "asserted", sources: [], first_seen: "2026-10-25T00:00:00Z" },
    }));
    mount(entityOf({ classification: { field: "marking" } }, { provenance: { state: "asserted" } }), { classification: "marking" }, vi.fn(), onPreviewHandling);
    fireEvent.click(screen.getByRole("button", { name: "Preview handling" }));
    await waitFor(() => expect(onPreviewHandling).toHaveBeenCalled());
    expect(onPreviewHandling).toHaveBeenCalledWith({ classification: { field: "marking" } }, { state: "asserted" });
  });
});

describe("ElementInspector: From column", () => {
  it("is disabled, and says Connect must declare it, when Connect declared no column for the part", () => {
    mount(entityOf({}), {});
    const option = fromColumn("classification");
    expect(option.disabled).toBe(true);
    expect(option.textContent).toContain("Connect must declare it first");
  });

  it("is disabled when the draft's declarations are not known at all", () => {
    mount(entityOf({}), undefined);
    expect(fromColumn("handling_code").disabled).toBe(true);
  });

  it("offers only the column Connect declared for that part", () => {
    mount(entityOf({}), { classification: "marking" });
    const option = fromColumn("classification");
    expect(option.disabled).toBe(false);
    expect(option.textContent).toContain("marking");
    const everything = Array.from(partBox("classification").options).map((o) => o.textContent).join("|");
    for (const other of COLUMNS.filter((c) => c !== "marking")) expect(everything).not.toContain(other);
    // A part with no declaration is not offered the declared column of another.
    expect(fromColumn("handling_code").disabled).toBe(true);
    expect(fromColumn("handling_code").textContent).not.toContain("marking");
  });

  it.each(Object.keys(LABELS))("writes {field: <column>} for %s", (part) => {
    const { onChangeEntity } = mount(entityOf({}), ALL_DECLARED);
    fireEvent.change(partBox(part), { target: { value: "__column__" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ handling: { [part]: { field: ALL_DECLARED[part as keyof typeof ALL_DECLARED] } } }),
    );
  });

  it("is offered for the six handling parts and for nothing else, provenance included", () => {
    mount(entityOf({}), ALL_DECLARED);
    const everyOption = screen.getAllByRole("option").filter((o) => o.textContent?.startsWith("From column"));
    expect(everyOption).toHaveLength(6);
    expect(screen.queryByLabelText(/provenance/i)).toBeNull();
  });
});

describe("ElementInspector: a part's literal value and its default", () => {
  it("writes a literal classification from the scheme's order", () => {
    const { onChangeEntity } = mount(entityOf({}), {});
    fireEvent.change(partBox("classification"), { target: { value: "SECRET" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(expect.objectContaining({ handling: { classification: "SECRET" } }));
  });

  it("offers the scheme's handling, action and sanitisation codes", () => {
    mount(entityOf({}), {});
    const codes = (part: string) =>
      Array.from(partBox(part).options).map((o) => o.value).filter((v) => v && v !== "__column__");
    expect(codes("handling_code")).toEqual(["P", "C", "R"]);
    expect(codes("action_code")).toEqual(["A1", "A2", "A3"]);
    expect(codes("sanitisation_code")).toEqual(["S1", "S2"]);
  });

  it("returns to the source default by dropping the part, leaving the others", () => {
    const { onChangeEntity } = mount(entityOf({ classification: { field: "marking" }, handling_code: "C" }), ALL_DECLARED);
    fireEvent.change(partBox("classification"), { target: { value: "" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(expect.objectContaining({ handling: { handling_code: "C" } }));
  });

  it("shows a literal unit already in the recipe, which it neither drops nor miscasts", () => {
    mount(entityOf({ originator: "unit-9" }), {});
    expect(partBox("originator").value).toBe("unit-9");
  });
});

describe("ElementInspector: a declared part an element does not bind", () => {
  const notice = () => screen.queryAllByRole("status").map((n) => n.textContent ?? "");

  it("names the part and its column, on an element with no override at all", () => {
    mount(entityOf(null), { classification: "marking" });
    expect(notice().join(" ")).toMatch(/does not bind Classification/);
    expect(notice().join(" ")).toContain("marking");
  });

  it("names each unbound part, and only those", () => {
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking", handling_code: "code" });
    expect(notice()).toHaveLength(1);
    expect(notice()[0]).toMatch(/Handling code/);
  });

  it("goes when the part is bound to the declared column", () => {
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking" });
    expect(notice()).toHaveLength(0);
  });

  it("stays when the part is bound to a column other than the declared one", () => {
    mount(entityOf({ classification: { field: "other" } }), { classification: "marking" });
    expect(notice().join(" ")).toMatch(/Classification/);
  });

  it("stays when the part carries a literal, which is not a binding", () => {
    mount(entityOf({ classification: "SECRET" }), { classification: "marking" });
    expect(notice().join(" ")).toMatch(/Classification/);
  });

  it("applies to an entity matched by reference, which is not exempt", () => {
    mount(entityOf(null, { on_match: "reference", match_on: "value_normalised" }), { classification: "marking" });
    expect(notice().join(" ")).toMatch(/Classification/);
  });

  it("applies to a link", () => {
    const edge: RecipeEdge = { type: "OWNS", from: "a", to: "b", handling: null } as RecipeEdge;
    render(
      <ElementInspector
        selection={{ kind: "edge", edge, fromType: "Endpoint", toType: "Endpoint" }}
        ontology={ONTOLOGY}
        transforms={[]}
        sourceFieldNames={COLUMNS}
        baselineClassification="OFFICIAL"
        classificationOrder={SCHEME.classification}
        handlingScheme={SCHEME}
        declaredColumns={{ owning_unit: "owner" }}
        onChangeEntity={vi.fn()}
        onChangeEdge={vi.fn()}
        onDelete={vi.fn()}
        onPreviewHandling={vi.fn()}
      />,
    );
    expect(notice().join(" ")).toMatch(/Owning unit/);
  });

  it("is not shown when Connect declared nothing", () => {
    mount(entityOf(null), {});
    expect(notice()).toHaveLength(0);
  });
});

describe("ElementInspector: the preview of a bound part", () => {
  const PREVIEW = {
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    provenance: { state: "asserted", sources: [], first_seen: "2026-10-25T00:00:00Z" },
  };

  it("says from column <name> for a bound part and gives the rest as the server did", async () => {
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking" }, vi.fn(), vi.fn(async () => PREVIEW));
    fireEvent.click(screen.getByRole("button", { name: "Preview handling" }));
    const line = await screen.findByText(/handling_code: P/);
    expect(line.textContent).toContain("classification: from column marking");
    expect(line.textContent).toContain("provenance: asserted");
    expect(line.textContent).not.toContain("classification: OFFICIAL");
  });

  it("gives the server's value for a part that is not bound", async () => {
    mount(entityOf({}), {}, vi.fn(), vi.fn(async () => PREVIEW));
    fireEvent.click(screen.getByRole("button", { name: "Preview handling" }));
    const line = await screen.findByText(/handling_code: P/);
    expect(line.textContent).toContain("classification: OFFICIAL");
  });

  it("names every bound part, not classification alone", async () => {
    mount(entityOf({ owning_unit: { field: "owner" } }), { owning_unit: "owner" }, vi.fn(), vi.fn(async () => PREVIEW));
    fireEvent.click(screen.getByRole("button", { name: "Preview handling" }));
    const line = await screen.findByText(/handling_code: P/);
    expect(line.textContent).toContain("owning_unit: from column owner");
  });
});

describe("ElementInspector: a binding to a column other than the declared one", () => {
  const optionOf = (part: string, text: string) =>
    Array.from(partBox(part).options).find((o) => o.textContent === text) as HTMLOptionElement | undefined;

  it("shows the column it holds as its own option, not as the declared column", () => {
    mount(entityOf({ classification: { field: "other" } }), { classification: "marking" });
    const shown = partBox("classification").selectedOptions[0]!;
    expect(shown.textContent).toBe("From column other (not declared)");
    expect(optionOf("classification", "From column marking")!.selected).toBe(false);
  });

  it("rebinds to the declared column when that is chosen", () => {
    const { onChangeEntity } = mount(entityOf({ classification: { field: "other" } }), { classification: "marking" });
    fireEvent.change(partBox("classification"), { target: { value: "__column__" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ handling: { classification: { field: "marking" } } }),
    );
  });

  it("changes nothing when the held column is chosen again", () => {
    const { onChangeEntity } = mount(entityOf({ classification: { field: "other" } }), { classification: "marking" });
    fireEvent.change(partBox("classification"), { target: { value: partBox("classification").value } });
    expect(onChangeEntity).not.toHaveBeenCalled();
  });

  it("agrees with the notice: both say the part is unbound until it is rebound, and neither after", () => {
    mount(entityOf({ classification: { field: "other" } }), { classification: "marking" });
    expect(partBox("classification").selectedOptions[0]!.textContent).toContain("not declared");
    expect(screen.getByRole("status").textContent).toMatch(/does not bind Classification.*marking/);
    cleanup();
    mount(entityOf({ classification: { field: "marking" } }), { classification: "marking" });
    expect(partBox("classification").selectedOptions[0]!.textContent).toBe("From column marking");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps a held column when Connect declares none for the part", () => {
    mount(entityOf({ handling_code: { field: "code" } }), {});
    expect(partBox("handling_code").selectedOptions[0]!.textContent).toBe("From column code (not declared)");
    expect(fromColumn("handling_code").disabled).toBe(true);
  });
});

describe("ElementInspector: a literal looser than the source's marking", () => {
  const SOURCE = {
    classification: "OFFICIAL",
    handling_code: "C",
    action_code: "A2",
    sanitisation_code: "S2",
  };
  const alerts = () => screen.queryAllByRole("alert").map((a) => a.textContent ?? "");

  it.each([
    ["handling_code", "P", /handling code/i],
    ["action_code", "A1", /action code/i],
    ["sanitisation_code", "S1", /sanitisation code/i],
    ["classification", "PUBLIC", /classification/i],
  ])("warns for %s %s", (part, value, label) => {
    mount(entityOf({ [part]: value }), {}, vi.fn(), vi.fn(), SOURCE);
    expect(alerts()).toHaveLength(1);
    expect(alerts()[0]).toMatch(/loosens the source/);
    expect(alerts()[0]).toMatch(label);
  });

  it.each([
    ["handling_code", "C"],
    ["handling_code", "R"],
    ["action_code", "A3"],
    ["sanitisation_code", "S2"],
    ["classification", "SECRET"],
  ])("does not warn for %s %s, which keeps or tightens", (part, value) => {
    mount(entityOf({ [part]: value }), {}, vi.fn(), vi.fn(), SOURCE);
    expect(alerts()).toHaveLength(0);
  });

  it("ranks an action code that needs the originator above one that does not, as merge_handling does", () => {
    mount(entityOf({ action_code: "A2" }), {}, vi.fn(), vi.fn(), { ...SOURCE, action_code: "A3" });
    expect(alerts()[0]).toMatch(/action code/i);
  });

  it("does not warn against a source that sets no action code: any code is at least as tight as none", () => {
    mount(entityOf({ action_code: "A1", handling_code: "P" }), {}, vi.fn(), vi.fn(), { classification: "OFFICIAL" });
    expect(alerts()).toHaveLength(0);
  });

  it("warns only where it can be computed: a source code the scheme does not define says nothing", () => {
    mount(entityOf({ handling_code: "P" }), {}, vi.fn(), vi.fn(), { ...SOURCE, handling_code: "Z" });
    expect(alerts()).toHaveLength(0);
  });

  it("does not warn for a part bound to a column, which the server judges per row", () => {
    mount(entityOf({ handling_code: { field: "code" } }), { handling_code: "code" }, vi.fn(), vi.fn(), SOURCE);
    expect(alerts()).toHaveLength(0);
  });
});
