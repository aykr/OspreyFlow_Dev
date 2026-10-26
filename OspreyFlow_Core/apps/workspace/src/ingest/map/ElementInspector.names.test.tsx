// @vitest-environment jsdom
//
// Rule 13: a control a keyboard test (or a screen reader) cannot name cannot be reached on purpose.
// The inspector's entity and link controls were named by a `<label>` beside them that pointed at
// nothing; each is now named, so it is found by the name a person would give it. The link's own type
// select is named apart from the list form's "Link type".
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RecipeEdge, RecipeEntity } from "../../../../../packages/schemas/generated";
import { ElementInspector } from "./ElementInspector";

afterEach(cleanup);

const ONTOLOGY = {
  version: 1,
  entity_types: [
    { name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle", properties: [] },
    { name: "Device", pole_class: "object", channel: "ochre", shape: "circle", properties: [] },
    { name: "Document", pole_class: "object", channel: "violet", shape: "page", properties: [] },
    { name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] },
  ],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct" },
    { name: "PAIRED_WITH", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
  ],
} as unknown as OntologySchema;

const ENTITY = { ref: "a", type: "Endpoint", pole_class: "object", on_match: "create", properties: {} } as RecipeEntity;
const EDGE = { type: "COMMUNICATED_WITH", from: "a", to: "b", properties: {} } as RecipeEdge;

function mount(selection: unknown) {
  const onChangeEntity = vi.fn();
  const onChangeEdge = vi.fn();
  render(
    <ElementInspector
      selection={selection as never}
      ontology={ONTOLOGY}
      transforms={[]}
      sourceFieldNames={["started", "ended"]}
      baselineClassification="OFFICIAL"
      classificationOrder={["OFFICIAL"]}
      onChangeEntity={onChangeEntity}
      onChangeEdge={onChangeEdge}
      onDelete={vi.fn()}
      onPreviewHandling={vi.fn()}
    />,
  );
  return { onChangeEntity, onChangeEdge };
}

describe("ElementInspector: an entity's controls are named", () => {
  it("names the POLE class, the type, the ref and match-on", () => {
    const { onChangeEntity } = mount({ kind: "entity", entity: ENTITY });
    expect((screen.getByLabelText("POLE class") as HTMLSelectElement).value).toBe("object");
    expect((screen.getByLabelText("Entity type") as HTMLSelectElement).value).toBe("Endpoint");
    expect((screen.getByLabelText("Entity ref") as HTMLInputElement).value).toBe("a");
    fireEvent.change(screen.getByLabelText("Match on"), { target: { value: "value_normalised" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(expect.objectContaining({ match_on: "value_normalised" }));
    fireEvent.change(screen.getByLabelText("POLE class"), { target: { value: "person" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ pole_class: "person", type: "Person" }),
    );
  });

  it("names the condition's column, test and value", () => {
    const { onChangeEntity } = mount({
      kind: "entity",
      entity: { ...ENTITY, when: { field: "started", equals: "x" } },
    });
    expect((screen.getByLabelText("Condition column") as HTMLSelectElement).value).toBe("started");
    expect((screen.getByLabelText("Condition test") as HTMLSelectElement).value).toBe("equals");
    fireEvent.change(screen.getByLabelText("Condition value"), { target: { value: "y" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ when: { field: "started", equals: "y" } }),
    );
  });
});

describe("ElementInspector: a link's own type is named apart from the form's", () => {
  it("names it 'Link type for this link'", () => {
    const { onChangeEdge } = mount({ kind: "edge", edge: EDGE, index: 0, fromType: "Endpoint", toType: "Endpoint" });
    const select = screen.getByLabelText("Link type for this link") as HTMLSelectElement;
    expect(select.value).toBe("COMMUNICATED_WITH");
    expect(screen.queryByLabelText("Link type")).toBeNull();
    fireEvent.change(select, { target: { value: "PAIRED_WITH" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ type: "PAIRED_WITH" }));
  });
});
