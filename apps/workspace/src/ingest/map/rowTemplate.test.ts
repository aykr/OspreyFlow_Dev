import { describe, expect, it } from "vitest";

import type {
  OntologySchema,
  RecipeEntity,
  RowTemplate,
} from "../../../../../packages/schemas/generated";
import {
  arityForTransform,
  classificationWouldLoosen,
  edgeTypesForEndpoints,
  entityTypesForPole,
  nextEntityRef,
  unmappedFieldNames,
} from "./rowTemplate";

function entity(overrides: Partial<RecipeEntity> = {}): RecipeEntity {
  return {
    ref: "e1",
    pole_class: "object",
    type: "Endpoint",
    on_match: "create",
    properties: {},
    ...overrides,
  };
}

describe("nextEntityRef", () => {
  it("starts at e1 for an empty template", () => {
    expect(nextEntityRef([])).toBe("e1");
  });

  it("skips refs already used, including a renamed one", () => {
    expect(nextEntityRef([entity({ ref: "e1" }), entity({ ref: "a" })])).toBe("e2");
  });
});

describe("entityTypesForPole / edgeTypesForEndpoints", () => {
  const ontology: OntologySchema = {
    version: 1,
    entity_types: [
      { name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle" },
      { name: "Location", pole_class: "location", channel: "jade", shape: "pin" },
    ],
    edge_types: [
      { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"] },
      { name: "PRESENT_AT", from: ["Endpoint"], to: ["Location"] },
      { name: "SAME_AS", from: ["Endpoint"], to: ["Endpoint"], system: true },
    ],
  };

  it("narrows entity types to the chosen POLE class", () => {
    expect(entityTypesForPole(ontology, "object").map((t) => t.name)).toEqual(["Endpoint"]);
  });

  it("offers only edge types valid for the two endpoint types, excluding system edges", () => {
    const types = edgeTypesForEndpoints(ontology, "Endpoint", "Location").map((t) => t.name);
    expect(types).toEqual(["PRESENT_AT"]);
  });
});

describe("arityForTransform", () => {
  it("defaults to 1 for a transform absent from the catalogue's arity", () => {
    expect(arityForTransform([{ name: "msisdn", arity: 1 }], "msisdn")).toBe(1);
  });

  it("reads a multi-column transform's declared arity", () => {
    expect(arityForTransform([{ name: "grid_ref", arity: 3 }], "grid_ref")).toBe(3);
  });

  it("defaults to 1 for no transform at all (a plain field binding)", () => {
    expect(arityForTransform([{ name: "grid_ref", arity: 3 }], null)).toBe(1);
  });
});

describe("unmappedFieldNames", () => {
  const template: RowTemplate = {
    entities: [
      entity({
        properties: {
          value_raw: { field: "a_party" },
          value_normalised: { field: "a_party", transform: "msisdn" },
        },
      }),
    ],
    edges: [],
  };

  it("lists a profiled column no binding references", () => {
    expect(unmappedFieldNames(["a_party", "imei"], template, new Set())).toEqual(["imei"]);
  });

  it("excludes a field explicitly marked ignore", () => {
    expect(unmappedFieldNames(["a_party", "imei"], template, new Set(["imei"]))).toEqual([]);
  });

  it("reads a multi-column `fields` binding, not just `field`", () => {
    const gridTemplate: RowTemplate = {
      entities: [
        entity({
          properties: {
            cell_identifier: { fields: ["grid_letters", "easting", "northing"], transform: "grid_ref" },
          },
        }),
      ],
      edges: [],
    };
    expect(
      unmappedFieldNames(["grid_letters", "easting", "northing", "imei"], gridTemplate, new Set()),
    ).toEqual(["imei"]);
  });
});

describe("classificationWouldLoosen", () => {
  const order = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"];

  it("is false with no override", () => {
    expect(classificationWouldLoosen(order, "OFFICIAL-SENSITIVE", null)).toBe(false);
  });

  it("is false when the override tightens", () => {
    expect(classificationWouldLoosen(order, "OFFICIAL-SENSITIVE", "SECRET")).toBe(false);
  });

  it("is true when the override loosens", () => {
    expect(classificationWouldLoosen(order, "OFFICIAL-SENSITIVE", "OFFICIAL")).toBe(true);
  });

  it("is false for an override equal to the baseline", () => {
    expect(classificationWouldLoosen(order, "OFFICIAL-SENSITIVE", "OFFICIAL-SENSITIVE")).toBe(false);
  });
});
