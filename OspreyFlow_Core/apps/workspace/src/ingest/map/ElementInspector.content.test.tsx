// @vitest-environment jsdom
// ADR-094 step 1: in Map, a link with a time can name the column holding its text, so each row's
// message or document becomes readable and extractable.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RecipeEdge } from "../../../../../packages/schemas/generated";
import { ElementInspector } from "./ElementInspector";

afterEach(cleanup);

const ONTOLOGY = {
  version: 11,
  entity_types: [{ name: "Endpoint", pole_class: "object", channel: "cyan", shape: "circle", properties: [] }],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct" },
    { name: "OWNS", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
  ],
} as unknown as OntologySchema;

function mount(edge: RecipeEdge, onChangeEdge = vi.fn()) {
  render(
    <ElementInspector
      selection={{ kind: "edge", edge, index: 0, fromType: "Endpoint", toType: "Endpoint" } as never}
      ontology={ONTOLOGY}
      transforms={[]}
      sourceFieldNames={["sender", "recipient", "sent_at", "text"]}
      baselineClassification="OFFICIAL"
      classificationOrder={["OFFICIAL"]}
      onChangeEntity={vi.fn()}
      onChangeEdge={onChangeEdge}
      onDelete={vi.fn()}
      onPreviewHandling={vi.fn()}
    />,
  );
  return onChangeEdge;
}

describe("ElementInspector: a link's text", () => {
  it("marks a column as the link's message text", () => {
    const onChangeEdge = mount({ type: "COMMUNICATED_WITH", from: "a", to: "b", temporal: { at: { field: "sent_at" } } });
    fireEvent.change(screen.getByLabelText("Text the model can read"), { target: { value: "message_text" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({ content: { kind: "message_text", field: "sender" } }),
    );
  });

  it("changes the column and can clear it", () => {
    const edge: RecipeEdge = {
      type: "COMMUNICATED_WITH",
      from: "a",
      to: "b",
      temporal: { at: { field: "sent_at" } },
      content: { kind: "message_text", field: "sender" },
    };
    const onChangeEdge = mount(edge);
    fireEvent.change(screen.getByLabelText("Column holding the text"), { target: { value: "text" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ content: { kind: "message_text", field: "text" } }));
    fireEvent.change(screen.getByLabelText("Text the model can read"), { target: { value: "" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ content: null }));
  });

  it("is not offered on a link with no time, which has no events to carry text", () => {
    mount({ type: "OWNS", from: "a", to: "b" });
    expect(screen.queryByLabelText("Text the model can read")).toBeNull();
  });
});
