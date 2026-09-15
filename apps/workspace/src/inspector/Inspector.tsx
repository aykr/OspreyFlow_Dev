import type { Node } from "../../../../packages/schemas/generated";
import { Panel } from "../design/primitives/Panel";
import { Tabs } from "../design/primitives/Tabs";
import { useState } from "react";

export interface InspectorProps {
  node: Node | null;
}

/** `docs/02_GLASS_FRONTEND.md` §2's workspace layout: "▸ Properties ▸
 * Provenance ▸ Relationships ▸ Judgements ▸ Source document" — Judgements
 * and Relationships are Phase 8/Phase 4-canvas-adjacent respectively and
 * out of this checkpoint's scope; Properties, Provenance and Source
 * document are what a single selected node actually needs shown now. */
export function Inspector({ node }: InspectorProps) {
  const [tab, setTab] = useState("properties");

  if (!node) {
    return (
      <Panel title="Inspector" className="inspector">
        <p style={{ color: "var(--text-tertiary)" }}>Select a node to inspect it.</p>
      </Panel>
    );
  }

  return (
    <Panel title="Inspector" className="inspector">
      <Tabs
        tabs={[
          { id: "properties", label: "Properties" },
          { id: "provenance", label: "Provenance" },
          { id: "source", label: "Source" },
        ]}
        activeId={tab}
        onChange={setTab}
      />
      {tab === "properties" && (
        <dl>
          <div>
            <dt style={{ color: "var(--text-secondary)" }}>Type</dt>
            <dd className="value">{node.type}</dd>
          </div>
          <div>
            <dt style={{ color: "var(--text-secondary)" }}>ID</dt>
            <dd className="identifier">{node.id}</dd>
          </div>
          {Object.entries(node.properties ?? {}).map(([key, value]) => (
            <div key={key}>
              <dt style={{ color: "var(--text-secondary)" }}>{key}</dt>
              <dd className="value">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {tab === "provenance" && (
        <div>
          <p>
            State: <span className="value">{node.provenance.state}</span>
          </p>
          <p>
            First seen: <span className="value">{node.provenance.first_seen}</span>
          </p>
        </div>
      )}
      {tab === "source" && (
        <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {node.provenance.sources.map((source, i) => (
            <li key={i} className="value">
              {source.document_id} · {source.locator}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
