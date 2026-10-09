// @vitest-environment jsdom
//
// 9 October 2026, the data engineer's journey: mapping a subscriber list's handsets, a Device offered
// no property at all. Its IMEI is declared as an identifier (`identifiers: [imei]`), not under
// `properties`, and Map offered only `properties`, though a recipe may set either (ontology
// validation knows both). An identifier is what a source most needs to set.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { OntologySchema } from "../../../../../packages/schemas/generated";
import { ElementInspector } from "./ElementInspector";

afterEach(cleanup);

const ONTOLOGY = {
  version: 12,
  entity_types: [
    { name: "Device", pole_class: "object", channel: "plum", shape: "square", identifiers: ["imei"], properties: [] },
    {
      name: "Person",
      pole_class: "person",
      channel: "indigo",
      shape: "circle",
      identifiers: ["nino"],
      properties: [{ name: "family_name", type: "string" }, { name: "nino", type: "string" }],
    },
  ],
  edge_types: [],
} as unknown as OntologySchema;

function offered(type: string): string[] {
  render(
    <ElementInspector
      selection={{ kind: "entity", entity: { ref: "e1", pole_class: "object", type, on_match: "create", properties: {} } } as never}
      ontology={ONTOLOGY}
      transforms={[]}
      sourceFieldNames={["imei"]}
      baselineClassification="OFFICIAL"
      classificationOrder={["OFFICIAL"]}
      onChangeEntity={vi.fn()}
      onChangeEdge={vi.fn()}
      onDelete={vi.fn()}
      onPreviewHandling={vi.fn()}
    />,
  );
  const select = screen.getByDisplayValue("+ property") as HTMLSelectElement;
  return [...select.options].map((o) => o.value).filter(Boolean);
}

it("offers a type's identifiers as well as its properties", () => {
  expect(offered("Device")).toEqual(["imei"]);
});

it("offers an identifier also declared as a property once, identifiers first", () => {
  expect(offered("Person")).toEqual(["nino", "family_name"]);
});
