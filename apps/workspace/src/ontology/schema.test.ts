import { describe, expect, it } from "vitest";

import type { OntologySchema } from "../../../../packages/schemas/generated";
import { OntologyRegistry } from "./schema";

function schema(): OntologySchema {
  return {
    version: 1,
    entity_types: [
      { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
      {
        name: "Endpoint",
        pole_class: "object",
        channel: "cyan",
        shape: "hexagon",
        identifiers: [],
      },
    ],
    edge_types: [],
  };
}

describe("OntologyRegistry", () => {
  it("looks up channel and shape by entity type name", () => {
    const registry = new OntologyRegistry(schema());

    expect(registry.visualFor("Person")).toEqual({ channel: "indigo", shape: "circle" });
    expect(registry.visualFor("Endpoint")).toEqual({ channel: "cyan", shape: "hexagon" });
  });

  it("returns undefined for an unknown entity type", () => {
    const registry = new OntologyRegistry(schema());

    expect(registry.visualFor("NoSuchType")).toBeUndefined();
  });

  it("throws at construction time for a shape the Glass has no generator for", () => {
    const bad: OntologySchema = {
      version: 1,
      entity_types: [
        {
          name: "Weird",
          pole_class: "object",
          channel: "ochre",
          shape: "octagon",
          identifiers: [],
        },
      ],
      edge_types: [],
    };

    expect(() => new OntologyRegistry(bad)).toThrow(/octagon/);
  });
});
