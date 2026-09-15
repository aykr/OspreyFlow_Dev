import { useEffect, useRef, useState } from "react";

import type { EdgeTypeDef, Node } from "../../../packages/schemas/generated";
import { GlassCanvas } from "./canvas/GlassCanvas";
import { Button } from "./design/primitives/Button";
import { Toast } from "./design/primitives/Toast";
import { HistoryPanel } from "./history/HistoryPanel";
import { Inspector } from "./inspector/Inspector";
import { fetchOntologyRegistry, type OntologyRegistry } from "./ontology/schema";
import { GlobalSearch } from "./search/GlobalSearch";
import { StatusBar } from "./statusbar/StatusBar";
import { connectDeltaClient, type SocketLike } from "./workingset/deltaClient";
import { createWorkingSet } from "./workingset/store";

// Dev-only: Phase 4's bullets do not include a login flow (OIDC/Keycloak's
// own UI is server-side, Phase 3's territory) — a bearer token supplied
// this way is a stand-in until a real sign-in screen exists, not a
// production auth path.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const DEV_BEARER_TOKEN = import.meta.env.VITE_DEV_BEARER_TOKEN ?? "";

function investigationIdFromSession(): string | null {
  return sessionStorage.getItem("ospreyflow.investigationId");
}

export function App() {
  const workingSetRef = useRef(createWorkingSet());
  const [investigationId, setInvestigationId] = useState<string | null>(investigationIdFromSession());
  const [ontology, setOntology] = useState<OntologyRegistry | null>(null);
  const [edgeTypes, setEdgeTypes] = useState<EdgeTypeDef[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [counts, setCounts] = useState({ nodes: 0, edges: 0, filteredCount: 0 });

  useEffect(() => {
    void fetchOntologyRegistry(API_BASE_URL, DEV_BEARER_TOKEN).then((registry) => {
      setOntology(registry);
    });
    void fetch(`${API_BASE_URL}/v1/ontology`, {
      headers: { Authorization: `Bearer ${DEV_BEARER_TOKEN}` },
    })
      .then((r) => r.json())
      .then((schema) => setEdgeTypes(schema.edge_types));
  }, []);

  useEffect(() => {
    if (investigationId) return;
    void fetch(`${API_BASE_URL}/v1/investigations`, {
      method: "POST",
      headers: { Authorization: `Bearer ${DEV_BEARER_TOKEN}` },
    })
      .then((r) => r.json())
      .then((investigation) => {
        sessionStorage.setItem("ospreyflow.investigationId", investigation.id);
        setInvestigationId(investigation.id);
      });
  }, [investigationId]);

  useEffect(() => {
    if (!investigationId) return;
    const workingSet = workingSetRef.current;
    const unsubscribe = workingSet.store.subscribe((state) => {
      setCounts({
        nodes: workingSet.graph.order,
        edges: workingSet.graph.size,
        filteredCount: state.filteredCount,
      });
      for (const notice of state.notices) {
        setToast(notice.message);
      }
    });

    const wsUrl = API_BASE_URL.replace(/^http/, "ws");
    // A browser's native `WebSocket` cannot set an `Authorization` header
    // — `?token=` is the server's documented fallback for exactly this
    // (`services/api/app.py`'s `_authenticate_websocket`).
    const client = connectDeltaClient(
      () =>
        new WebSocket(
          `${wsUrl}/v1/investigations/${investigationId}/stream?token=${encodeURIComponent(DEV_BEARER_TOKEN)}`,
        ) as unknown as SocketLike,
      { onDelta: (delta) => workingSet.store.getState().applyDelta(delta) },
    );
    return () => {
      client.close();
      unsubscribe();
    };
  }, [investigationId]);

  if (!investigationId || !ontology) {
    return <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-16)",
          padding: "var(--sp-8) var(--sp-16)",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <strong>Case {investigationId.slice(0, 8)}</strong>
        <div style={{ flex: 1, maxWidth: 480 }}>
          <GlobalSearch
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            onSelect={(node) => {
              workingSetRef.current.store.getState().applyDelta({
                seq: workingSetRef.current.store.getState().seq,
                op: "add",
                nodes: [node],
                edges: [],
              });
              setSelectedNode(node);
            }}
          />
        </div>
        <Button onClick={() => setHistoryOpen(true)}>History</Button>
      </header>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <GlassCanvas
            graph={workingSetRef.current.graph}
            store={workingSetRef.current.store}
            ontology={ontology}
            edgeTypes={edgeTypes}
            investigationId={investigationId}
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            onSelectionChange={(nodeIds) => {
              const first = nodeIds[0];
              const graph = workingSetRef.current.graph;
              setSelectedNode(first && graph.hasNode(first) ? graph.getNodeAttribute(first, "data") : null);
            }}
          />
        </div>
        <div style={{ width: 320, borderLeft: "1px solid var(--border-subtle)" }}>
          <Inspector node={selectedNode} />
        </div>
      </div>
      <StatusBar
        nodeCount={counts.nodes}
        edgeCount={counts.edges}
        dimmedCount={0}
        filteredCount={counts.filteredCount}
      />
      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        investigationId={investigationId}
        apiBaseUrl={API_BASE_URL}
        bearerToken={DEV_BEARER_TOKEN}
        onRestored={(snapshot) => workingSetRef.current.store.getState().applyDelta(snapshot)}
      />
      {toast && (
        <div style={{ position: "fixed", bottom: 16, right: 16 }}>
          <Toast message={toast} />
        </div>
      )}
    </div>
  );
}
