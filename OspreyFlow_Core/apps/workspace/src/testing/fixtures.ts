// Minimal, valid domain fixtures for frontend unit tests — mirrors the
// shape `tests/conformance/graph_port/test_suite.py`'s own `_node`/`_edge`
// helpers build server-side, kept intentionally small since these tests
// exercise the Glass's own logic (the store, the delta client), not the
// domain model itself.
import type { Edge, Node } from "../../../../packages/schemas/generated";

export function makeNode(id: string, overrides: Partial<Node> = {}): Node {
  return {
    id,
    type: "Person",
    provenance: {
      state: "asserted",
      sources: [{ document_id: "doc-1", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "loader-1" },
    ...overrides,
  };
}

export function makeEdge(
  id: string,
  source: string,
  target: string,
  overrides: Partial<Edge> = {},
): Edge {
  return {
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    provenance: {
      state: "asserted",
      sources: [{ document_id: "doc-1", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "loader-1" },
    ...overrides,
  };
}
