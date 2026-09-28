import { useEffect, useState } from "react";

import type { OntologyRegistry } from "../ontology/schema";
import type { WorkingSetGraph } from "../workingset/store";
import { fetchDocumentView } from "./api";
import { HighlightedMessage } from "./HighlightedMessage";
import type { DocumentView } from "./models";

export interface DossierProps {
  graph: WorkingSetGraph;
  ontology: OntologyRegistry;
  nodeId: string;
  investigationId: string;
  apiBaseUrl: string;
  bearerToken: string;
  onSelectNode?: (nodeId: string) => void;
}

/** `spec/00_ARCHITECTURE.md`'s own component diagram names the Dossier a peer of Canvas/Timeline/
 * Map/Query, not an Inspector tab or a canvas overlay — `02_GLASS_FRONTEND.md`'s own cross-
 * references from Stage 2/3's transient popovers already treat it as the larger, permanent
 * surface neither should pre-empt. `08_ACCEPTANCE_SCENARIOS.md` B6: "Inspect the shared
 * endpoint's messages... message content renders with the entity spans highlighted in place." */
export function Dossier({
  graph,
  ontology,
  nodeId,
  investigationId,
  apiBaseUrl,
  bearerToken,
  onSelectNode,
}: DossierProps) {
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!graph.hasNode(nodeId)) {
      setDocuments([]);
      setLoading(false);
      return;
    }
    // `Node.provenance.sources` is already synced to this session via the working set — no new
    // call needed to learn which documents mention this entity.
    const node = graph.getNodeAttribute(nodeId, "data");
    const documentIds = [...new Set(node.provenance.sources.map((s) => s.document_id))];
    let cancelled = false;
    setLoading(true);
    void Promise.all(
      documentIds.map((id) => fetchDocumentView(apiBaseUrl, bearerToken, investigationId, id)),
    ).then((views) => {
      if (cancelled) return;
      setDocuments(views.filter((v): v is DocumentView => v !== null));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [graph, nodeId, investigationId, apiBaseUrl, bearerToken]);

  if (loading) {
    return <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>Loading messages…</div>;
  }

  if (documents.length === 0) {
    return (
      <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>
        No messages found for this endpoint.
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        overflow: "auto",
        padding: "var(--sp-24)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-16)",
      }}
    >
      {documents.map((doc) => (
        <div key={doc.document_id} className="panel" style={{ padding: "var(--sp-16)" }}>
          <HighlightedMessage document={doc} ontology={ontology} onSelectNode={onSelectNode} />
        </div>
      ))}
    </div>
  );
}
