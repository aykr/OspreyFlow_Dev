import type Graph from "graphology";
import type { Judgement, Node } from "../../../../packages/schemas/generated";
import { JudgementsPanel } from "../assessment/JudgementsPanel";
import { Panel } from "../design/primitives/Panel";
import { Tabs } from "../design/primitives/Tabs";
import { LinkDetails, type LinkDetailsProps } from "./LinkDetails";
import { LinkNotes } from "./LinkNotes";
import { useState } from "react";

export interface InspectorProps {
  node: Node | null;
  /** A selected link. While one is, the Inspector shows it instead of a node. */
  link?: LinkDetailsProps | null;
  /** Phase 8 Stage 4c: the Judgements tab, `02_GLASS_FRONTEND.md` §9. `undefined` when the
   * caller has not wired assessment production up yet (an existing test harness) — the tab is
   * then simply not offered, the same optional-prop pattern `dimmedNodeIds`/`communityHulls`
   * already establish on `GlassCanvas` for exactly this reason. */
  assessment?: {
    apiBaseUrl: string;
    bearerToken: string;
    investigationId: string;
    workingSetGraph: Graph;
    onHighlightNodes: (nodeIds: string[]) => void;
    /** Told the full list of judgements each time the panel has fetched it, so the canvas can keep
     * the count beside each node current (ADR-070). */
    onJudgementsChange?: (judgements: Judgement[]) => void;
  };
}

/** `spec/02_GLASS_FRONTEND.md` §2's workspace layout: "▸ Properties ▸
 * Provenance ▸ Relationships ▸ Judgements ▸ Source document" — Relationships
 * is out of this checkpoint's scope; Properties, Provenance, Source document
 * and (Phase 8 Stage 4c) Judgements are what this Inspector now covers.
 *
 * **The Judgements tab does not require a selected node** — unlike
 * Properties/Provenance/Source, assessment production is investigation-
 * scoped, not node-scoped (`02_GLASS_FRONTEND.md` §9's own framing: the
 * analytical product, not a per-node fact) — so `Tabs` renders even when
 * `node` is `null`, with only the node-specific tabs' own content gated on
 * it. */
export function Inspector({ node, link, assessment }: InspectorProps) {
  const [tab, setTab] = useState("properties");

  if (link) {
    return (
      <Panel title="Inspector" className="inspector">
        <LinkDetails {...link} />
        {/* ADR-075: notes belong to a case, so they are offered only where one is open. */}
        {assessment && (
          <LinkNotes
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            edgeId={link.edge.id}
          />
        )}
      </Panel>
    );
  }

  if (!node && !assessment) {
    return (
      <Panel title="Inspector" className="inspector">
        <p style={{ color: "var(--text-tertiary)" }}>Select a node to inspect it.</p>
      </Panel>
    );
  }

  const tabs = [
    { id: "properties", label: "Properties" },
    { id: "provenance", label: "Provenance" },
    { id: "source", label: "Source" },
    ...(assessment ? [{ id: "judgements", label: "Judgements" }] : []),
  ];
  const activeTab = node ? tab : "judgements";

  return (
    <Panel title="Inspector" className="inspector">
      <Tabs tabs={tabs} activeId={activeTab} onChange={setTab} />
      {activeTab === "judgements" && assessment && (
        <JudgementsPanel
          apiBaseUrl={assessment.apiBaseUrl}
          bearerToken={assessment.bearerToken}
          investigationId={assessment.investigationId}
          workingSetGraph={assessment.workingSetGraph}
          selectedNodeId={node?.id ?? null}
          onHighlightNodes={assessment.onHighlightNodes}
          onJudgementsChange={assessment.onJudgementsChange}
        />
      )}
      {!node && activeTab !== "judgements" && (
        <p style={{ color: "var(--text-tertiary)" }}>Select a node to inspect it.</p>
      )}
      {node && tab === "properties" && (
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
      {node && tab === "provenance" && (
        <div>
          <p>
            State: <span className="value">{node.provenance.state}</span>
          </p>
          <p>
            First seen: <span className="value">{node.provenance.first_seen}</span>
          </p>
        </div>
      )}
      {node && tab === "source" && (
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
