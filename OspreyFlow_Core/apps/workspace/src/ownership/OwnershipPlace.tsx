// The *Ownership* place on the left rail (`06_DECISIONS.md` ADR-109 phase C, rulings 5 and 9):
// enhanced due diligence on one organisation or account — who ultimately owns or controls it,
// through every layer, with cumulative shares. A share is the product of a chain's percentages,
// summed over chains; a link with no stated percentage makes the share unknown (never assumed);
// control is control, not a share; a circle of cross-holdings is traced once and said. Everything
// is as the reader reads it, and nothing here is written to the graph.
import { useState } from "react";
import type { Edge, Node, OwnershipView, OwnerTrace } from "../../../../packages/schemas/generated";
import { Button, Input } from "../design/primitives";
import { nodeName } from "../alerts/names";
import type { CanvasOutcome } from "../alerts/api";
import { findEntities, ownershipToCanvas, traceOwnership, type OwnershipApi } from "./api";

export interface OwnershipPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string | null;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
}

const PERCENT = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

export function percent(value: number): string {
  return `${PERCENT.format(value)}%`;
}

/** One chain in words, owner first: "Petrov → Aegean Fiduciary Trust (60%) → … ". */
export function describeChain(linkIds: string[], edges: Map<string, Edge>, names: Map<string, string>): string {
  const parts: string[] = [];
  linkIds.forEach((id, i) => {
    const edge = edges.get(id);
    if (!edge) return;
    if (i === 0) parts.push(names.get(edge.source) ?? "?");
    const raw = (edge.properties as Record<string, unknown>).percent;
    const how =
      edge.type === "CONTROLS" ? "controls" : typeof raw === "number" ? percent(raw) : "share not stated";
    parts.push(`${names.get(edge.target) ?? "?"} (${how})`);
  });
  return parts.join(" → ");
}

export function ownerNotes(owner: OwnerTrace): string[] {
  const notes: string[] = [];
  if (owner.beneficial_owner) notes.push("Beneficial owner");
  if (owner.possible_beneficial_owner) notes.push("Possible beneficial owner — share partly unknown");
  if (owner.controls) notes.push("Controls");
  if (owner.share_unknown && !owner.possible_beneficial_owner) notes.push("Share partly unknown");
  return notes;
}

export function OwnershipPlace(props: OwnershipPlaceProps) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Node[] | null>(null);
  const [target, setTarget] = useState<Node | null>(null);
  const [threshold, setThreshold] = useState("25");
  const [view, setView] = useState<OwnershipView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [openChains, setOpenChains] = useState<string | null>(null);

  if (!investigationId) return <p className="label">Open a case to trace ownership in it.</p>;
  const api: OwnershipApi = { apiBaseUrl, bearerToken, investigationId };

  const trace = (node: Node, share: string) => {
    setTarget(node);
    setProblem(null);
    setSaid(null);
    setView(null);
    const value = Number(share);
    if (!(value > 0 && value <= 100)) {
      setProblem("The threshold is a percentage above 0 and at most 100.");
      return;
    }
    traceOwnership(api, node.id, value)
      .then(setView)
      .catch((e: Error) => setProblem(e.message));
  };

  const names = new Map((view?.nodes ?? []).map((n) => [n.id, nodeName(n)]));
  const edges = new Map((view?.edges ?? []).map((e) => [e.id, e]));
  const owners = view?.trace.owners ?? [];
  const beneficial = owners.filter((o) => o.beneficial_owner || o.possible_beneficial_owner);

  return (
    <section aria-label="Ownership" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", overflowY: "auto", flex: 1 }}>
      <h2 className="value" style={{ margin: 0 }}>Ownership</h2>
      <form
        aria-label="Find an entity to trace"
        onSubmit={(e) => {
          e.preventDefault();
          setProblem(null);
          findEntities(api, query.trim())
            .then(setFound)
            .catch((err: Error) => setProblem(err.message));
        }}
        style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}
      >
        <label className="label" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          Organisation or account
          <Input aria-label="Organisation or account" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <Button type="submit" disabled={query.trim().length < 2}>
          Find
        </Button>
        <label className="label" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          Beneficial owner at (%)
          <Input
            type="number"
            step="1"
            aria-label="Beneficial ownership threshold"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            style={{ width: 90 }}
          />
        </label>
        {target && (
          <Button type="button" onClick={() => trace(target, threshold)}>
            Trace again
          </Button>
        )}
      </form>
      {found !== null && found.length === 0 && <p className="label">Nothing by that name in this case.</p>}
      {found !== null && found.length > 0 && (
        <ul aria-label="Matching entities" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--sp-8)" }}>
          {found.map((node) => (
            <li key={node.id}>
              <Button aria-pressed={target?.id === node.id} onClick={() => trace(node, threshold)}>
                Trace {nodeName(node)}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
      {said && <p role="status" className="label">{said}</p>}
      {view && target && (
        <>
          <h3 className="value" style={{ margin: 0 }}>Who stands behind {nodeName(target)}</h3>
          {beneficial.length === 0 ? (
            <p className="label">No natural person reaches the {percent(view.trace.threshold)} threshold or holds control, in what you can see.</p>
          ) : (
            <p>
              Beneficial owners at {percent(view.trace.threshold)}:{" "}
              {beneficial.map((o) => `${names.get(o.node_id) ?? "?"} (${percent(o.cumulative_percent)}${o.controls ? ", controls" : ""}${o.possible_beneficial_owner ? ", possibly more" : ""})`).join("; ")}
            </p>
          )}
          {view.trace.cycles?.map((cycle) => (
            <p key={cycle.join("|")} className="label" style={{ color: "var(--warning)" }}>
              A circle of cross-holdings: {cycle.map((id) => names.get(id) ?? "?").join(", ")} — traced once, not round and round.
            </p>
          ))}
          <table className="table" aria-label="Every owner and controller">
            <thead>
              <tr>
                <th>Party</th>
                <th>Type</th>
                <th style={{ textAlign: "right" }}>Cumulative share</th>
                <th>Notes</th>
                <th>Chains</th>
              </tr>
            </thead>
            <tbody>
              {owners.map((owner) => (
                <tr key={owner.node_id}>
                  <td>{names.get(owner.node_id) ?? "?"}</td>
                  <td>{owner.node_type}</td>
                  <td style={{ textAlign: "right" }}>
                    {owner.share_unknown ? "at least " : ""}
                    {percent(owner.cumulative_percent)}
                  </td>
                  <td>{ownerNotes(owner).join(" · ")}</td>
                  <td>
                    <Button
                      aria-expanded={openChains === owner.node_id}
                      aria-label={`Chains from ${names.get(owner.node_id) ?? "?"}`}
                      onClick={() => setOpenChains(openChains === owner.node_id ? null : owner.node_id)}
                    >
                      {(owner.paths ?? []).length}
                    </Button>
                    {openChains === owner.node_id && (
                      <ul aria-label={`Chains from ${names.get(owner.node_id) ?? "?"}, listed`} style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
                        {(owner.paths ?? []).map((path) => (
                          <li key={path.link_ids.join("|")} className="label">
                            {describeChain(path.link_ids, edges, names)}
                            {path.kind === "ownership" && path.share != null ? ` = ${percent(path.share)}` : path.kind === "control" ? " — control" : " — share unknown"}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div>
            <Button
              onClick={() =>
                void ownershipToCanvas(api, target.id)
                  .then((outcome) => {
                    setSaid(`${outcome.added_nodes} node(s) and ${outcome.added_links} link(s) added to the canvas.`);
                    props.onCanvas(outcome, (view.nodes ?? []).map((n) => n.id));
                  })
                  .catch((e: Error) => setProblem(e.message))
              }
            >
              Show the structure on the canvas
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
