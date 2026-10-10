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

// --- ownership (06_DECISIONS.md ADR-109 phase C) — the same walk and the same order as Tier 2's
// `adapters/compute_rustworkx/ownership.py`, so the two agree to the last bit: chains sorted by
// their link ids, shares multiplied owner first, summed in chain order.
const MAX_CHAINS = 20000;

function compareIds(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return a.length - b.length;
}

function ownershipPath(links) {
  const ids = links.map((l) => l.id);
  if (links.some((l) => l.kind === "controls")) return { link_ids: ids, kind: "control", share: null };
  if (links.some((l) => l.percent === null || l.percent === undefined)) {
    return { link_ids: ids, kind: "unknown", share: null };
  }
  let share = 100.0;
  for (const l of links) share = (share * l.percent) / 100;
  return { link_ids: ids, kind: "ownership", share };
}

function ownershipCycles(links) {
  const graph = new Map();
  const nodes = new Set();
  const selfOwned = new Set();
  for (const l of links) {
    if (!graph.has(l.source)) graph.set(l.source, []);
    graph.get(l.source).push(l.target);
    nodes.add(l.source);
    nodes.add(l.target);
    if (l.source === l.target) selfOwned.add(l.source);
  }
  const index = new Map();
  const low = new Map();
  const onStack = new Set();
  const stack = [];
  const found = [];
  let counter = 0;
  for (const root of [...nodes].sort()) {
    if (index.has(root)) continue;
    const work = [[root, 0]];
    while (work.length) {
      const [node, child] = work.pop();
      if (child === 0) {
        index.set(node, counter);
        low.set(node, counter);
        counter += 1;
        stack.push(node);
        onStack.add(node);
      }
      const successors = [...(graph.get(node) ?? [])].sort();
      if (child < successors.length) {
        work.push([node, child + 1]);
        const next = successors[child];
        if (!index.has(next)) work.push([next, 0]);
        else if (onStack.has(next)) low.set(node, Math.min(low.get(node), index.get(next)));
        continue;
      }
      if (low.get(node) === index.get(node)) {
        const component = [];
        for (;;) {
          const member = stack.pop();
          onStack.delete(member);
          component.push(member);
          if (member === node) break;
        }
        if (component.length > 1 || selfOwned.has(node)) found.push(component.sort());
      }
      if (work.length) {
        const parent = work[work.length - 1][0];
        low.set(parent, Math.min(low.get(parent), low.get(node)));
      }
    }
  }
  return found.sort(compareIds);
}

function ownership(request) {
  const types = new Map(request.nodes.map((n) => [n.id, n.type]));
  const into = new Map();
  for (const l of request.links) {
    if (!into.has(l.target)) into.set(l.target, []);
    into.get(l.target).push(l);
  }
  for (const incoming of into.values()) incoming.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const maxDepth = request.max_depth ?? 10;
  const threshold = request.threshold ?? 25;
  const chains = new Map();
  let count = 0;
  const work = [[request.target, [], new Set([request.target])]];
  while (work.length) {
    const [node, links, seen] = work.pop();
    for (const link of into.get(node) ?? []) {
      const owner = link.source;
      if (seen.has(owner)) continue;
      const chain = [link, ...links];
      if (chain.length > maxDepth) {
        throw new Error(`a chain of more than ${maxDepth} links reaches the target; the structure is not traced in part`);
      }
      count += 1;
      if (count > MAX_CHAINS) throw new Error(`more than ${MAX_CHAINS} chains reach the target; the structure is not traced in part`);
      if (!chains.has(owner)) chains.set(owner, []);
      chains.get(owner).push(ownershipPath(chain));
      work.push([owner, chain, new Set([...seen, owner])]);
    }
  }
  const owners = [];
  for (const [owner, paths] of chains) {
    paths.sort((a, b) => compareIds(a.link_ids, b.link_ids));
    let cumulative = 0.0;
    for (const p of paths) if (p.kind === "ownership" && p.share !== null) cumulative += p.share;
    const unknown = paths.some((p) => p.kind === "unknown");
    const controls = paths.some((p) => p.kind === "control");
    const person = types.get(owner) === "Person";
    const beneficial = person && (cumulative >= threshold || controls);
    owners.push({
      node_id: owner,
      node_type: types.get(owner) ?? "unknown",
      cumulative_percent: cumulative,
      share_unknown: unknown,
      controls,
      paths,
      beneficial_owner: beneficial,
      possible_beneficial_owner: person && !beneficial && unknown,
    });
  }
  owners.sort((a, b) => b.cumulative_percent - a.cumulative_percent || (a.node_id < b.node_id ? -1 : a.node_id > b.node_id ? 1 : 0));
  return { target: request.target, threshold, owners, cycles: ownershipCycles(request.links) };
}

// --- risk propagation (06_DECISIONS.md ADR-109 phase E) — Tier 2's
// `adapters/compute_rustworkx/propagation.py`, operation for operation: breadth-first shortest
// distances, the decay factor by repeated multiplication, contributions sorted then summed.
function propagate(request) {
  const around = new Map();
  const link = (a, b) => {
    if (!around.has(a)) around.set(a, new Set());
    around.get(a).add(b);
  };
  for (const e of request.edges) {
    link(e.source, e.target);
    link(e.target, e.source);
  }
  const maxHops = request.max_hops ?? 2;
  const decay = request.decay ?? 0.5;
  const hops = new Map([[request.target, 0]]);
  const queue = [request.target];
  while (queue.length) {
    const node = queue.shift();
    if (hops.get(node) === maxHops) continue;
    for (const next of [...(around.get(node) ?? [])].sort()) {
      if (!hops.has(next)) {
        hops.set(next, hops.get(node) + 1);
        queue.push(next);
      }
    }
  }
  const contributions = [];
  for (const [nodeId, seed] of Object.entries(request.seeds)) {
    if (!hops.has(nodeId) || seed <= 0) continue;
    let factor = 1.0;
    for (let i = 0; i < hops.get(nodeId); i += 1) factor = factor * decay;
    contributions.push({ node_id: nodeId, hops: hops.get(nodeId), seed, contribution: seed * factor });
  }
  contributions.sort((a, b) => b.contribution - a.contribution || (a.node_id < b.node_id ? -1 : a.node_id > b.node_id ? 1 : 0));
  let score = 0.0;
  for (const c of contributions) score = score + c.contribution;
  return { target: request.target, score, contributions };
}

function dispatch(method, request) {
  if (method === "centrality") return centrality(request.subgraph, request.metric);
  if (method === "communities") return communities(request.subgraph);
  if (method === "ownership") return ownership(request);
  if (method === "propagate") return propagate(request);
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
