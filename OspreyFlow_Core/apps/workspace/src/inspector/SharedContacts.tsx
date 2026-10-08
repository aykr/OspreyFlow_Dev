// Who shares contacts with the selected node (ADR-100 Amendment 7 decision 4): asked of this node
// alone, which keeps it quick (0.5 s for the busiest Enron address, where the same question over
// the whole case ran for minutes), by each link type the node can have contacts by. Counted in the
// store as the analyst; a pick puts the two and the contacts they share on the canvas, all or none.
import { useState } from "react";

import type { EdgeTypeDef, Node } from "../../../../packages/schemas/generated";
import { nodeLabel } from "../canvas/nodeAttributes";
import { linkTypeName } from "../canvas/linkLabel";
import type { SharedContacts as Found } from "../../../../packages/schemas/generated";
import type { WorkingSetDelta } from "../workingset/models";

const COUNT = new Intl.NumberFormat("en-GB");

export interface SharedContactsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  node: Node;
  edgeTypes: readonly EdgeTypeDef[];
  /** Applies what a pick put in the case's working set to the canvas. */
  onDelta: (delta: WorkingSetDelta) => void;
}

function plural(n: number, one: string, many: string): string {
  return `${COUNT.format(n)} ${n === 1 ? one : many}`;
}

function nodeUrl(props: SharedContactsProps, path: string): string {
  return `${props.apiBaseUrl}/v1/investigations/${encodeURIComponent(props.investigationId)}/nodes/${encodeURIComponent(props.node.id)}/${path}`;
}

/** The link types this node can have contacts by: its own type at their start, not a system type. */
function contactTypes(node: Node, edgeTypes: readonly EdgeTypeDef[]): EdgeTypeDef[] {
  return edgeTypes.filter((e) => !e.system && e.from.includes(node.type) && e.to.length > 0);
}

function ByType({ props, edgeType }: { props: SharedContactsProps; edgeType: EdgeTypeDef }) {
  const [found, setFound] = useState<Found | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const name = linkTypeName(edgeType.name, props.edgeTypes);
  const headers = { Authorization: `Bearer ${props.bearerToken}` };
  const query = `edge_type=${encodeURIComponent(edgeType.name)}`;

  async function ask() {
    setBusy(true);
    setProblem(null);
    try {
      const response = await fetch(nodeUrl(props, `shared-contacts?${query}`), { headers });
      if (!response.ok) throw new Error(`Who shares contacts could not be read (${response.status}).`);
      setFound((await response.json()) as Found);
    } catch (err: unknown) {
      setProblem(err instanceof Error && err.message.startsWith("Who") ? err.message : "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  async function pick(other: Node) {
    setBusy(true);
    setSaid(null);
    try {
      const response = await fetch(
        nodeUrl(props, `shared-contacts/${encodeURIComponent(other.id)}/canvas?${query}`),
        { method: "POST", headers },
      );
      const body = (await response.json().catch(() => ({}))) as {
        delta?: WorkingSetDelta;
        added_nodes?: number;
        added_links?: number;
        error?: string;
        cap_kind?: string;
        cap?: number;
        would_be?: number;
      };
      if (response.ok && body.delta) {
        props.onDelta(body.delta);
        setSaid(`${plural(body.added_nodes ?? 0, "node", "nodes")} and ${plural(body.added_links ?? 0, "link", "links")} added.`);
      } else if (body.error === "limit_exceeded") {
        setSaid(`Too many for the canvas: ${COUNT.format(body.would_be ?? 0)} ${body.cap_kind ?? "nodes"} against a limit of ${COUNT.format(body.cap ?? 0)}.`);
      } else if (body.error === "too_many_matches") {
        setSaid("They share too many contacts to add at once.");
      } else if (response.status === 403) {
        setSaid("Adding to this case needs Editor access.");
      } else {
        setSaid(`They could not be added (${response.status}).`);
      }
    } catch {
      setSaid("The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  const caption = { color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 };
  return (
    <li style={{ display: "grid", gap: "var(--sp-4)" }}>
      <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void ask()}>
        {`Who shares two contacts by “${name}”?`}
      </button>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {found && found.total === 0 && <p style={caption}>Nobody you can see shares two.</p>}
      {found && found.total > 0 && (
        <>
          <p style={caption}>
            {found.contacts.length < found.total
              ? `The ${COUNT.format(found.contacts.length)} who share most of ${COUNT.format(found.total)}.`
              : `All ${COUNT.format(found.total)} shown.`}
          </p>
          <ol style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" }}>
            {found.contacts.map((c) => (
              <li key={c.node.id}>
                <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void pick(c.node)}>
                  {`${nodeLabel(c.node)} · shares ${COUNT.format(c.shared)}`}
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
      {said && (
        <p aria-live="polite" style={{ margin: 0 }}>
          {said}
        </p>
      )}
    </li>
  );
}

export function SharedContacts(props: SharedContactsProps) {
  const types = contactTypes(props.node, props.edgeTypes);
  if (types.length === 0) {
    return <p style={{ margin: 0, color: "var(--text-tertiary)" }}>This type has no contacts to share.</p>;
  }
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "var(--sp-8)" }}>
      {types.map((t) => (
        <ByType key={`${props.node.id}|${t.name}`} props={props} edgeType={t} />
      ))}
    </ul>
  );
}
