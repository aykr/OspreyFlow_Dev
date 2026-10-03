import type { Edge, Node } from "../../../../packages/schemas/generated";
import { displayValue } from "../search/searchOptions";

export interface LinkDetailsProps {
  edge: Edge;
  /** The nodes at each end, when they are on screen. An end that is not falls back to its id. */
  source: Node | undefined;
  target: Node | undefined;
  /** Whether the ontology gives this type of relationship a direction. */
  directed: boolean;
}

/** What the Inspector shows when a link is selected: its type, the direction between its two
 * ends, how many records stand behind it, its dates and its sources. */
export function LinkDetails({ edge, source, target, directed }: LinkDetailsProps) {
  const from = source ? displayValue(source) : edge.source;
  const to = target ? displayValue(target) : edge.target;
  const sources = edge.provenance.sources;
  return (
    <dl>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Link</dt>
        <dd className="value">{edge.type}</dd>
      </div>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Between</dt>
        <dd className="value">
          {directed ? `${from} → ${to}` : `${from} — ${to}`}
          {directed ? "" : " (no direction)"}
        </dd>
      </div>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Records behind it</dt>
        <dd className="value">{edge.occurrences ?? 1}</dd>
      </div>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Dates</dt>
        <dd className="value">
          {edge.interval
            ? `${edge.interval.valid_from} – ${edge.interval.valid_to ?? "present"}`
            : "No dates recorded"}
        </dd>
      </div>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Provenance</dt>
        <dd className="value">{edge.provenance.state}</dd>
      </div>
      <div>
        <dt style={{ color: "var(--text-secondary)" }}>Sources</dt>
        <dd>
          {sources.length === 0 ? (
            "No sources recorded"
          ) : (
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {sources.map((s, i) => (
                <li key={i} className="value">
                  {s.document_id} · {s.locator}
                </li>
              ))}
            </ul>
          )}
        </dd>
      </div>
    </dl>
  );
}
