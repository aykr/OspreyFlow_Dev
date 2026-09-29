#!/usr/bin/env node
// `ComputePort` Tier 1 — `spec/00_ARCHITECTURE.md` §2.3, `spec/06_DECISIONS.md` ADR-028's own
// decision: exercised as a plain Node script, never a browser or a `Worker`. The correctness
// claim `tests/conformance/compute_port/test_suite.py` exists to prove is algorithmic —
// graphology's numbers agree with `rustworkx`'s on the same input — not a threading claim; a real
// browser `Worker`'s message-passing is a separate, frontend-owned concern this script does not
// address (ADR-028's own docstring has the full reasoning).
//
// Protocol: one JSON object on stdin — `{ "method": "centrality" | "communities" |
// "clique_metric", "request": {...} }`, matching `packages/schemas/compute.py`'s own request
// shapes (`subgraph.nodes[].id`, `subgraph.edges[].source/target/weight` are all this script
// reads; every other `Node`/`Edge` field is irrelevant to the algorithm and ignored) — one JSON
// result object on stdout, then exit. No persistent process, no IPC beyond one request/response,
// matching this ADR's own "a small Node script... headless" characterisation.
import Graph from "graphology";
import betweennessCentrality from "graphology-metrics/centrality/betweenness.js";
import eigenvectorCentrality from "graphology-metrics/centrality/eigenvector.js";
import pagerank from "graphology-metrics/centrality/pagerank.js";
import { weightedUndirectedDegree } from "graphology-metrics/node/weighted-degree.js";
import louvain from "graphology-communities-louvain";

import { splitDisconnectedCommunities } from "./communities.mjs";

// `01_DOMAIN_MODEL.md` §6.2's own stated boundaries, filled the same way
// `packages/adapters/compute_rustworkx/adapter.py`'s own `_saturate` is: linear from 0 at
// `k_min` to 1 at `k_max` — the simplest monotonic choice consistent with both stated boundaries,
// duplicated here rather than shared, the same reasoning as `splitDisconnectedCommunities`'s own
// module docstring.
function saturate(n, kMin, kMax) {
  if (n <= kMin) return 0;
  if (n >= kMax) return 1;
  return (n - kMin) / (kMax - kMin);
}

// Neither `rustworkx` nor `graphology-metrics` has a per-node local clustering coefficient
// function (`06_DECISIONS.md` ADR-028's own finding, confirmed again here rather than assumed
// still true) — implemented directly, identical formula to the Python adapter's own
// `_local_density_and_degree`: `density(v) = internal(v) / possible(v)`, the standard local
// clustering coefficient. Shared by `clustering_coefficient` and `clique_metric` rather than
// computed twice.
function localDensityAndDegree(graph, node) {
  const neighbours = graph.neighbors(node);
  const k = neighbours.length;
  if (k < 2) return { density: 0, degree: k, neighbours };
  let internal = 0;
  for (let i = 0; i < neighbours.length; i++) {
    for (let j = i + 1; j < neighbours.length; j++) {
      if (graph.hasEdge(neighbours[i], neighbours[j])) internal += 1;
    }
  }
  const possible = (k * (k - 1)) / 2;
  return { density: internal / possible, degree: k, neighbours };
}

// `external(v) / sum(degree(u) for u in neighbours)` — `01_DOMAIN_MODEL.md` §6.2.
function dispersion(graph, node, neighbours) {
  const within = new Set(neighbours);
  within.add(node);
  let external = 0;
  let degreeSum = 0;
  for (const u of neighbours) {
    degreeSum += graph.degree(u);
    for (const w of graph.neighbors(u)) {
      if (!within.has(w)) external += 1;
    }
  }
  if (degreeSum === 0) return 0;
  return external / degreeSum;
}

function buildGraph(subgraph) {
  const graph = new Graph({ type: "undirected", multi: true });
  for (const node of subgraph.nodes) graph.addNode(node.id);
  for (const edge of subgraph.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    graph.addUndirectedEdge(edge.source, edge.target, { weight: edge.weight ?? 0 });
  }
  return graph;
}

const CENTRALITY_OPTIONS = { getEdgeWeight: null, maxIterations: 1000, tolerance: 1e-10 };

function centrality(subgraph, metric) {
  const graph = buildGraph(subgraph);
  const nodeIds = subgraph.nodes.map((n) => n.id);

  if (metric === "degree") {
    return Object.fromEntries(nodeIds.map((id) => [id, graph.degree(id)]));
  }
  if (metric === "weighted_degree") {
    return Object.fromEntries(
      nodeIds.map((id) => [id, weightedUndirectedDegree(graph, id, "weight")]),
    );
  }
  if (metric === "betweenness") {
    return betweennessCentrality(graph, { getEdgeWeight: null, normalized: true });
  }
  if (metric === "eigenvector") {
    return eigenvectorCentrality(graph, CENTRALITY_OPTIONS);
  }
  if (metric === "pagerank") {
    return pagerank(graph, { ...CENTRALITY_OPTIONS, alpha: 0.85 });
  }
  if (metric === "clustering_coefficient") {
    return Object.fromEntries(
      nodeIds.map((id) => [id, localDensityAndDegree(graph, id).density]),
    );
  }
  throw new Error(`unsupported centrality metric: ${metric}`);
}

function communities(subgraph) {
  const graph = buildGraph(subgraph);
  const nodeIds = subgraph.nodes.map((n) => n.id);
  const edgePairs = subgraph.edges
    .filter((e) => graph.hasNode(e.source) && graph.hasNode(e.target))
    .map((e) => [e.source, e.target]);

  const rawPartition = louvain(graph, { getEdgeWeight: null });
  return splitDisconnectedCommunities(nodeIds, edgePairs, rawPartition);
}

function cliqueMetric(subgraph, kMin, kMax) {
  const graph = buildGraph(subgraph);
  const result = {};
  for (const node of subgraph.nodes) {
    const { density, degree, neighbours } = localDensityAndDegree(graph, node.id);
    const disp = dispersion(graph, node.id, neighbours);
    const sat = saturate(degree, kMin, kMax);
    result[node.id] = density * (1 - disp) * sat;
  }
  return result;
}

function dispatch(method, request) {
  if (method === "centrality") return centrality(request.subgraph, request.metric);
  if (method === "communities") return communities(request.subgraph);
  if (method === "clique_metric") {
    return cliqueMetric(request.subgraph, request.k_min ?? 4, request.k_max ?? 30);
  }
  throw new Error(`unsupported ComputePort method for Tier 1: ${method}`);
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

const raw = await readStdin();
const { method, request } = JSON.parse(raw);
try {
  const result = dispatch(method, request);
  process.stdout.write(JSON.stringify({ result }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: String(error && error.message ? error.message : error) }));
  process.exitCode = 1;
}
