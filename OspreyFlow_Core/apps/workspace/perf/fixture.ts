// The 50k-node/250k-edge performance fixture — `spec/02_GLASS_FRONTEND.md`
// §5's performance budget table names this exact shape as the measurement
// baseline. Synthetic and in-repo, standing rule 9: a seeded
// pseudo-random generator, no real intelligence data.
import type { Edge, Node } from "../../../packages/schemas/generated";

export const FIXTURE_NODE_COUNT = 50_000;
export const FIXTURE_EDGE_COUNT = 250_000;

const ENTITY_TYPES = ["Person", "Endpoint", "Device", "Organisation", "Location"] as const;

function mulberry32(seed: number): () => number {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeNode(id: string, type: string): Node {
  return {
    id,
    type,
    properties: { family_name: id },
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

function makeEdge(id: string, source: string, target: string): Edge {
  return {
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    weight: 1,
    occurrences: 1,
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

export function generateFixture(
  nodeCount: number = FIXTURE_NODE_COUNT,
  edgeCount: number = FIXTURE_EDGE_COUNT,
): { nodes: Node[]; edges: Edge[] } {
  const random = mulberry32(42);
  const nodes: Node[] = [];
  for (let i = 0; i < nodeCount; i++) {
    const type = ENTITY_TYPES[i % ENTITY_TYPES.length]!;
    nodes.push(makeNode(`n${i}`, type));
  }
  const edges: Edge[] = [];
  for (let i = 0; i < edgeCount; i++) {
    const a = Math.floor(random() * nodeCount);
    let b = Math.floor(random() * nodeCount);
    if (b === a) b = (b + 1) % nodeCount;
    edges.push(makeEdge(`e${i}`, `n${a}`, `n${b}`));
  }
  return { nodes, edges };
}
