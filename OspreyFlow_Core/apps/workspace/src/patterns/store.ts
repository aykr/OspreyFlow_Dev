// The visual query builder's own pattern state — Phase 7 Stage 4, `01_DOMAIN_MODEL.md` §8.1 /
// `06_DECISIONS.md` ADR-030. Pure state and derivation, no React: `QueryBuilderPanel.tsx` is the
// only consumer, the same "logic separate from the component" split `metrics/hulls.ts` keeps from
// `MetricsPanel.tsx`.
//
// **Root/pin validation mirrors `MatchBuilder._render_matched`'s own derivation
// (`packages/adapters/graph_arcadedb/builders.py`) on purpose, not by coincidence** — ADR-030's
// "explained at the point of drawing" standard only holds if the canvas's own idea of "which node
// is an unpinned second root" is the same one the compiler will reject at Run. A root is a node
// with no incoming pattern edge; the primary root is the first unpinned root (or `nodes[0]` if
// every root happens to be pinned already, matching the compiler's own tie-break); every other
// root must carry a `pinnedNodeId`.
import type {
  OntologySchema,
  PatternEdge,
  PatternNode,
  PatternQuery,
  PropertyDef,
} from "../../../../packages/schemas/generated";

/** ADR-121: the most conditions one node may carry (`PATTERN_WHERE_MAX` in `schemas/domain.py`). */
export const MAX_CONDITIONS = 3;

export interface PatternNodeState {
  var: string;
  entityType: string;
  pinnedNodeId: string | null;
  /** Display label for a pinned node (`"Person · n42"`) — `null` for an ordinary variable. */
  pinnedLabel: string | null;
  /** ADR-121: property name to the one value it must equal; empty for none. */
  where: Record<string, string>;
}

export interface PatternEdgeState {
  edgeType: string;
  fromVar: string;
  toVar: string;
}

export interface PatternBuilderState {
  nodes: PatternNodeState[];
  edges: PatternEdgeState[];
}

export function createEmptyPattern(): PatternBuilderState {
  return { nodes: [], edges: [] };
}

/** The next unused single-letter variable name — `a`, `b`, `c`, ... A 26-node pattern is already
 * far past what a canvas this small is meant to hold (`02_GLASS_FRONTEND.md` §3.3's own "a
 * handful of pattern nodes" framing), so exhaustion is a real, disclosed ceiling, not a rename
 * scheme worth generalising ahead of an actual need for it. */
export function nextVarName(state: PatternBuilderState): string {
  const used = new Set(state.nodes.map((n) => n.var));
  for (let i = 0; i < 26; i++) {
    const candidate = String.fromCharCode(97 + i);
    if (!used.has(candidate)) return candidate;
  }
  throw new Error("pattern already uses all 26 single-letter variable names");
}

export function addVariableNode(
  state: PatternBuilderState,
  entityType: string,
): PatternBuilderState {
  const nodeVar = nextVarName(state);
  return {
    ...state,
    nodes: [
      ...state.nodes,
      { var: nodeVar, entityType, pinnedNodeId: null, pinnedLabel: null, where: {} },
    ],
  };
}

export function pinNode(
  state: PatternBuilderState,
  entityType: string,
  nodeId: string,
  label: string,
): PatternBuilderState {
  const nodeVar = nextVarName(state);
  return {
    ...state,
    nodes: [
      ...state.nodes,
      { var: nodeVar, entityType, pinnedNodeId: nodeId, pinnedLabel: label, where: {} },
    ],
  };
}

export function addEdge(
  state: PatternBuilderState,
  edgeType: string,
  fromVar: string,
  toVar: string,
): PatternBuilderState {
  return { ...state, edges: [...state.edges, { edgeType, fromVar, toVar }] };
}

/** Removes a pattern node (and every edge touching it) by its variable name — the canvas has
 * nothing else a focused element could be keyed by, since `var` is assigned once, at creation,
 * and never reused within one pattern. */
export function removeElement(state: PatternBuilderState, nodeVar: string): PatternBuilderState {
  return {
    nodes: state.nodes.filter((n) => n.var !== nodeVar),
    edges: state.edges.filter((e) => e.fromVar !== nodeVar && e.toVar !== nodeVar),
  };
}

/** The properties of a type a condition may name (ADR-121): indexed, text (a string or an enum:
 * the value is one string), and not `sensitivity: high`. The server checks the same rule and
 * refuses by name; this only keeps the field from offering what would be refused. */
export function conditionableProperties(schema: OntologySchema, entityType: string): PropertyDef[] {
  const type = schema.entity_types.find((t) => t.name === entityType);
  return (type?.properties ?? []).filter(
    (p) => p.indexed === true && p.sensitivity !== "high" && (p.type === "string" || p.type === "enum"),
  );
}

/** Sets a node's condition on one property to one value. An empty value is not a condition and
 * changes nothing; a property already held takes the new value; a fourth property is not added. */
export function addCondition(
  state: PatternBuilderState,
  nodeVar: string,
  property: string,
  value: string,
): PatternBuilderState {
  const trimmed = value.trim();
  if (!property || trimmed === "") return state;
  return {
    ...state,
    nodes: state.nodes.map((n) => {
      if (n.var !== nodeVar) return n;
      if (!(property in n.where) && Object.keys(n.where).length >= MAX_CONDITIONS) return n;
      return { ...n, where: { ...n.where, [property]: trimmed } };
    }),
  };
}

export function removeCondition(
  state: PatternBuilderState,
  nodeVar: string,
  property: string,
): PatternBuilderState {
  return {
    ...state,
    nodes: state.nodes.map((n) => {
      if (n.var !== nodeVar) return n;
      const rest = { ...n.where };
      delete rest[property];
      return { ...n, where: rest };
    }),
  };
}

function roots(state: PatternBuilderState): PatternNodeState[] {
  const toVars = new Set(state.edges.map((e) => e.toVar));
  return state.nodes.filter((n) => !toVars.has(n.var));
}

/** Every root beyond the primary one that is not yet pinned — non-empty exactly when the pattern
 * is, right now, in the state `MatchBuilder._render_matched` would reject at Run with "an open
 * second root has no general join on this adapter." The canvas surfaces this the instant it
 * becomes true, not only when Preview/Run is pressed. */
/** Whether the compiler walks the whole pattern from its first variable (`MatchBuilder.
 * _render_single_chain`, ADR-100 Amendment 7): it takes next any link from a variable already
 * reached, any link back from one to a new unpinned variable, or any link between two reached, in
 * whatever order they were drawn. A pattern it cannot walk falls to the pinned-root rule below. */
function walksFromTheFirst(state: PatternBuilderState): boolean {
  const first = state.nodes[0];
  if (!first) return false;
  const pinned = new Set(state.nodes.filter((n) => n.pinnedNodeId !== null).map((n) => n.var));
  const reached = new Set([first.var]);
  const pending = [...state.edges];
  for (;;) {
    const next = pending.findIndex(
      (e) => reached.has(e.fromVar) || (reached.has(e.toVar) && !pinned.has(e.fromVar)),
    );
    if (next < 0) break;
    const [edge] = pending.splice(next, 1);
    reached.add(edge!.fromVar);
    reached.add(edge!.toVar);
  }
  return pending.length === 0 && state.nodes.every((n) => reached.has(n.var));
}

export function unpinnedSecondaryRoots(state: PatternBuilderState): PatternNodeState[] {
  if (walksFromTheFirst(state)) return [];
  const patternRoots = roots(state);
  if (patternRoots.length <= 1) return [];
  // `patternRoots[0]` is guaranteed by the length check above — `noUncheckedIndexedAccess`
  // cannot see that from the check alone, so the assertion documents what the guard already
  // proves rather than silencing a real gap.
  const primary = patternRoots.find((r) => r.pinnedNodeId === null) ?? patternRoots[0]!;
  return patternRoots.filter((r) => r.var !== primary.var && r.pinnedNodeId === null);
}

export function isPatternRunnable(state: PatternBuilderState): boolean {
  return state.nodes.length > 0 && unpinnedSecondaryRoots(state).length === 0;
}

export function toPatternQuery(state: PatternBuilderState, limit = 1000): PatternQuery {
  const nodes: PatternNode[] = state.nodes.map((n) => ({
    var: n.var,
    entity_type: n.entityType,
    node_id: n.pinnedNodeId,
    // Sent only when there is one, so a pattern with no condition is the pattern it always was.
    ...(Object.keys(n.where).length > 0 ? { where: { ...n.where } } : {}),
  }));
  const edges: PatternEdge[] = state.edges.map((e) => ({
    edge_type: e.edgeType,
    from_var: e.fromVar,
    to_var: e.toVar,
  }));
  return { nodes, edges, limit };
}

/** The inverse of `toPatternQuery`, for loading a saved pattern back into the builder
 * (`06_DECISIONS.md` ADR-032/036/040). `pinnedLabel` is display-only and was never persisted in
 * `PatternQuery` itself, so it is regenerated here in the same `"${entityType} · ${nodeId}"` shape
 * `handlePinFromSearch` already produces at pin time — the two are indistinguishable once
 * rendered, which is the point: a reloaded pinned node looks exactly like one just pinned. */
export function fromPatternQuery(definition: PatternQuery): PatternBuilderState {
  return {
    nodes: definition.nodes.map((n) => ({
      var: n.var,
      entityType: n.entity_type ?? "",
      pinnedNodeId: n.node_id ?? null,
      pinnedLabel: n.node_id ? `${n.entity_type} · ${n.node_id}` : null,
      where: { ...(n.where ?? {}) },
    })),
    edges: definition.edges.map((e) => ({
      edgeType: e.edge_type,
      fromVar: e.from_var,
      toVar: e.to_var,
    })),
  };
}
