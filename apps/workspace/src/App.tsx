import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  EdgeTypeDef,
  GeoBin,
  Node,
  OntologySchema,
  PublicMapConfig,
  Sighting,
} from "../../../packages/schemas/generated";
import { fetchGeoBins, fetchSightings } from "./analytics/api";
import { GlassCanvas, type GlassCanvasHandle } from "./canvas/GlassCanvas";
import {
  buildEventFilter,
  createCrossFilterStore,
  type CrossFilterStore,
  type CrossFilterStoreState,
} from "./crossfilter/store";
import { Button } from "./design/primitives/Button";
import { Toast } from "./design/primitives/Toast";
import { Dossier } from "./dossier/Dossier";
import { ExportPanel } from "./export/ExportPanel";
import { HistoryPanel } from "./history/HistoryPanel";
import { Inspector } from "./inspector/Inspector";
import { computeCommunityHulls } from "./metrics/hulls";
import { MetricsPanel } from "./metrics/MetricsPanel";
import { QueryBuilderPanel } from "./patterns/QueryBuilderPanel";
import { ResolutionThresholdControl } from "./resolution/ThresholdControl";
import { resolveNodeCoordinates } from "./map/geometries";
import { HotspotHistogram } from "./map/HotspotHistogram";
import { MapView } from "./map/MapView";
import { defaultProvider, fetchMapConfig } from "./map/providers";
import { instantAtFraction, itemsUpTo } from "./playback/math";
import {
  fetchOntologyRegistry,
  type OntologyRegistry,
} from "./ontology/schema";
import { GlobalSearch } from "./search/GlobalSearch";
import { BoundaryFilterTool } from "./map/BoundaryFilterTool";
import { IngestStudio } from "./ingest/IngestStudio";
import { SiteCalibrationWizard } from "./site/SiteCalibrationWizard";
import { StatusBar } from "./statusbar/StatusBar";
import { Timeline } from "./timeline/Timeline";
import { AlertInbox } from "./watches/AlertInbox";
import { HotlistPanel } from "./watches/HotlistPanel";
import { MonitorPanel } from "./watches/MonitorPanel";
import { connectDeltaClient, type SocketLike } from "./workingset/deltaClient";
import { createWorkingSet } from "./workingset/store";

// Dev-only: Phase 4's bullets do not include a login flow (OIDC/Keycloak's
// own UI is server-side, Phase 3's territory) — a bearer token supplied
// this way is a stand-in until a real sign-in screen exists, not a
// production auth path.
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const DEV_BEARER_TOKEN = import.meta.env.VITE_DEV_BEARER_TOKEN ?? "";

// A stable reference, not `new Map()` inline in JSX — used only as
// `nodeCoordinates` state's initial value below (never recreated on every
// render): an unstable reference here would force `MapView` to tear down
// and rebuild its whole MapLibre/Sigma instance on every single render of
// `App` — harmless in isolation, but a real infinite loop once anything
// downstream (`onMapReady`) feeds a fresh map instance back into this
// component's own state on every rebuild. Found via manual verification of
// the site geospatial wizard, not by inspection — recorded here rather
// than worked around in `MapView`. Real coordinates now come from
// `resolveNodeCoordinates` (`map/geometries.ts`), Checkpoint 2's
// `AnalyticsPort.get_geometries` HTTP wiring.
const EMPTY_NODE_COORDINATES = new Map<string, { lat: number; lng: number }>();

// Same stable-reference reasoning as `EMPTY_NODE_COORDINATES` above — this
// feeds `GlassCanvas`'s `dimmedNodeIds` prop, which its own effect keys a
// `useEffect` dependency array off (`canvas/GlassCanvas.tsx`).
const EMPTY_DIMMED_NODE_IDS: ReadonlySet<string> = new Set();

const EMPTY_GEO_BINS: readonly GeoBin[] = [];

// `GeoBinRequest.precision`'s own doc comment: "higher is finer, each step
// halving the latitude span a bin covers." 8 is this checkpoint's fixed
// starting point — a zoom-linked precision is a real refinement, not
// needed for A1/A2's fixed-site scale.
const GEO_BIN_PRECISION = 8;

function investigationIdFromSession(): string | null {
  return sessionStorage.getItem("ospreyflow.investigationId");
}

export function App() {
  const workingSetRef = useRef(createWorkingSet());
  const glassCanvasRef = useRef<GlassCanvasHandle>(null);
  const [investigationId, setInvestigationId] = useState<string | null>(
    investigationIdFromSession(),
  );
  // Phase 7 Stage 3: the metrics panel's own "Show community hulls" toggle feeds this, `App.tsx`
  // (not `MetricsPanel` itself) turns it into hull geometry — `MetricsPanel` has no dependency on
  // Sigma/the canvas at all, the same separation `onSelectionChange`/`onViewMessages` already draw
  // between "what happened" and "what the canvas does about it."
  const [communities, setCommunities] = useState<Record<string, string> | null>(null);
  const [ontology, setOntology] = useState<OntologyRegistry | null>(null);
  const [edgeTypes, setEdgeTypes] = useState<EdgeTypeDef[]>([]);
  // The full schema, not only `OntologyRegistry`'s own channel/shape lookup — Phase 7 Stage 4's
  // `QueryBuilderPanel` needs the entity/edge type *names* to populate its own palette and connect
  // controls, which `OntologyRegistry` was never built to expose. Captured from the same `/v1
  // /ontology` fetch `edgeTypes` already comes from, not a third redundant request.
  const [ontologySchema, setOntologySchema] = useState<OntologySchema | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  // B16's own cross-case overlay — the second investigation's own scope,
  // analyst-entered (this build has no cross-investigation picker anywhere
  // yet; typing the id directly is this stage's own minimal, real input,
  // not a placeholder for a picker that doesn't exist).
  const [crossCaseScope, setCrossCaseScope] = useState("");
  // B18's own playback fraction, reported by `Timeline`'s own clock
  // (`playback/usePlayback.ts`) and consumed here to filter `sightings`
  // down to what the map's own snail trail should currently reveal.
  const [playbackFraction, setPlaybackFraction] = useState(0);
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [counts, setCounts] = useState({
    nodes: 0,
    edges: 0,
    filteredCount: 0,
  });
  const [view, setView] = useState<"graph" | "map" | "ingest" | "dossier" | "watches">("graph");
  const [dossierNodeId, setDossierNodeId] = useState<string | null>(null);
  const [mapConfig, setMapConfig] = useState<PublicMapConfig | null>(null);
  const [siteWizardOpen, setSiteWizardOpen] = useState(false);
  const [boundaryToolOpen, setBoundaryToolOpen] = useState(false);
  const [liveMap, setLiveMap] = useState<MapLibreMap | null>(null);
  // Constructed once `investigationId` is known — `investigationScope` is
  // frozen into the store at creation (`crossfilter/store.ts`), and
  // `investigationId` only ever moves from `null` to a real id once per
  // session, never changes again, so a lazy ref assignment during render
  // (rather than an effect) is safe here.
  const crossFilterRef = useRef<CrossFilterStore | null>(null);
  if (investigationId && !crossFilterRef.current) {
    crossFilterRef.current = createCrossFilterStore(
      API_BASE_URL,
      DEV_BEARER_TOKEN,
      investigationId,
    );
  }
  const [dimming, setDimming] = useState({
    dimmedNodeIds: EMPTY_DIMMED_NODE_IDS,
    dimmedCount: 0,
  });
  const [nodeCoordinates, setNodeCoordinates] = useState(EMPTY_NODE_COORDINATES);
  const [geoBins, setGeoBins] = useState<readonly GeoBin[]>(EMPTY_GEO_BINS);

  useEffect(() => {
    void fetchOntologyRegistry(API_BASE_URL, DEV_BEARER_TOKEN).then(
      (registry) => {
        setOntology(registry);
      },
    );
    void fetch(`${API_BASE_URL}/v1/ontology`, {
      headers: { Authorization: `Bearer ${DEV_BEARER_TOKEN}` },
    })
      .then((r) => r.json())
      .then((schema: OntologySchema) => {
        setEdgeTypes(schema.edge_types);
        setOntologySchema(schema);
      });
    void fetchMapConfig(API_BASE_URL, DEV_BEARER_TOKEN).then(setMapConfig);
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
      // A delta can add/remove working-set nodes the cross-filter has never
      // seen — re-derive dimming against the current membership so a newly
      // streamed-in node gets its correct dimmed state right away, per
      // `crossfilter/store.ts`'s own `refresh` doc comment. A no-op fast
      // path when no filter is active (`refresh`'s own early return).
      void crossFilterRef.current?.refresh(workingSet.graph.nodes());
      // Likewise, a delta can add a `Location` node the map has never
      // plotted — re-resolve every working-set `Location`'s geometry_ref
      // whenever membership changes. A no-op fast path when the working
      // set has no `Location` nodes yet (`resolveNodeCoordinates`'s own
      // early return).
      void resolveNodeCoordinates(API_BASE_URL, DEV_BEARER_TOKEN, workingSet.graph).then(
        setNodeCoordinates,
      );
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

  useEffect(() => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter) return;
    const unsubscribe = crossFilter.store.subscribe((state) => {
      setDimming({
        dimmedNodeIds: state.dimmedNodeIds,
        dimmedCount: state.dimmedCount,
      });
    });
    return () => unsubscribe();
  }, [investigationId]);

  useEffect(() => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter || !investigationId) return;
    const scope = investigationId;
    // Unlike the timeline's own density strip (`timeline/Timeline.tsx`'s
    // own comment on why it always shows the full range), the map's heat
    // layer *does* restrict to the active brush window — `02_GLASS_
    // FRONTEND.md` §3.4's "the map restricts to it" is this bullet, named
    // literally.
    async function refresh(state: CrossFilterStoreState) {
      const filter = buildEventFilter(scope, state.window, state.selectedNodeIds);
      const bins = await fetchGeoBins(API_BASE_URL, DEV_BEARER_TOKEN, {
        filter,
        precision: GEO_BIN_PRECISION,
      });
      setGeoBins(bins);
    }
    let lastWindow = crossFilter.store.getState().window;
    let lastSelected = crossFilter.store.getState().selectedNodeIds;
    void refresh(crossFilter.store.getState());
    const unsubscribe = crossFilter.store.subscribe((state) => {
      if (state.window === lastWindow && state.selectedNodeIds === lastSelected) return;
      lastWindow = state.window;
      lastSelected = state.selectedNodeIds;
      void refresh(state);
    });
    return () => unsubscribe();
  }, [investigationId]);

  // B18's own snail trail — one entity's own ordered sightings over the
  // active brush window. "The device's sightings" (`08_ACCEPTANCE_
  // SCENARIOS.md` B18) generalises here to whichever node the analyst has
  // currently selected in the Inspector — this build has no separate
  // "pick an entity for the trail" control, and the Inspector's own
  // selection is already the entity an analyst is looking at. No window
  // set, or no node selected: no fetch, and the trail is empty.
  useEffect(() => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter || !investigationId || !selectedNode) {
      setSightings([]);
      return;
    }
    const scope = investigationId;
    const entityId = selectedNode.id;
    let cancelled = false;
    function refresh(window: CrossFilterStoreState["window"]) {
      if (!window) {
        setSightings([]);
        return;
      }
      void fetchSightings(API_BASE_URL, DEV_BEARER_TOKEN, {
        filter: buildEventFilter(scope, window, [entityId]),
      }).then((result) => {
        if (!cancelled) setSightings(result);
      });
    }
    refresh(crossFilter.store.getState().window);
    const unsubscribe = crossFilter.store.subscribe((state) => refresh(state.window));
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [investigationId, selectedNode]);

  // The revealed prefix of `sightings` at the current playback position —
  // recomputed on every animation frame (`playbackFraction` changes), the
  // real content change B18's own "animates under playback" names, not a
  // CSS trick layered over a static list.
  const revealedSightings = useMemo(() => {
    const crossFilter = crossFilterRef.current;
    const window = crossFilter?.store.getState().window;
    if (!window || sightings.length === 0) return sightings;
    return itemsUpTo(sightings, instantAtFraction(window, playbackFraction));
  }, [sightings, playbackFraction]);

  // Recomputed only when the fetched `communities` result itself changes, not on every render —
  // `metrics/hulls.ts`'s own benchmark (2.6ms at the 20k-node sync boundary) makes per-render
  // recomputation affordable in principle, but `useMemo` avoids paying it for unrelated App-level
  // re-renders (a Toast firing, the status bar ticking) that touch neither `communities` nor the
  // graph. Known, disclosed staleness: a reproject that moves node positions without a fresh
  // `communities` fetch does not itself refresh hull vertices until the next fetch — real, and
  // left rather than adding a second recompute trigger this stage's own plan did not call for.
  //
  // Declared before the "not ready yet" early return below, per the rules of Hooks — every Hook
  // in this component must run on every render, loading state included.
  const communityHulls = useMemo(
    () => (communities ? computeCommunityHulls(workingSetRef.current.graph, communities) : undefined),
    [communities],
  );

  if (!investigationId || !ontology || !crossFilterRef.current) {
    return (
      <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>
        Loading…
      </div>
    );
  }
  const crossFilterStore = crossFilterRef.current;

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
        <Button
          aria-pressed={view === "graph"}
          onClick={() => setView("graph")}
        >
          Graph
        </Button>
        <Button aria-pressed={view === "map"} onClick={() => setView("map")}>
          Map
        </Button>
        <Button aria-pressed={view === "ingest"} onClick={() => setView("ingest")}>
          Ingest
        </Button>
        <Button aria-pressed={view === "watches"} onClick={() => setView("watches")}>
          Watches
        </Button>
        {dossierNodeId && (
          <Button aria-pressed={view === "dossier"} onClick={() => setView("dossier")}>
            Messages
          </Button>
        )}
        {view === "graph" && (
          <ResolutionThresholdControl
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            investigationId={investigationId}
            store={workingSetRef.current.store}
            onChangeSummary={setToast}
          />
        )}
        {view === "graph" && (
          // `02_GLASS_FRONTEND.md` §2's own workspace-layout mockup: "Resolution: ●Balanced
          // Export ⚙" — the top-bar trigger for the export drawer (§10).
          <Button aria-pressed={exportOpen} onClick={() => setExportOpen((open) => !open)}>
            Export ⚙
          </Button>
        )}
        {view === "map" && (
          <Button
            aria-pressed={siteWizardOpen}
            onClick={() => setSiteWizardOpen((open) => !open)}
          >
            Add site
          </Button>
        )}
        {view === "map" && (
          <Button
            aria-pressed={boundaryToolOpen}
            onClick={() => setBoundaryToolOpen((open) => !open)}
          >
            Draw boundary
          </Button>
        )}
        <Button onClick={() => setHistoryOpen(true)}>History</Button>
      </header>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {view === "ingest" && (
          <IngestStudio
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            investigationId={investigationId}
          />
        )}
        {view === "dossier" && dossierNodeId && (
          <Dossier
            graph={workingSetRef.current.graph}
            ontology={ontology}
            nodeId={dossierNodeId}
            investigationId={investigationId}
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            onSelectNode={(nodeId) => {
              const graph = workingSetRef.current.graph;
              setSelectedNode(graph.hasNode(nodeId) ? graph.getNodeAttribute(nodeId, "data") : null);
              setView("graph");
            }}
          />
        )}
        {view === "watches" && (
          // Owner-only, not investigation-scoped — the same reasoning `/v1/patterns/*` already
          // gives (`patterns/api.ts`'s own module docstring) — so this view, like "ingest" and
          // "dossier", opts out of the investigation-scoped side panel/timeline/status bar below
          // rather than being squeezed into `view === "graph"`'s own 320px column.
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--sp-8)", overflowY: "auto", padding: "var(--sp-8)" }}>
            <HotlistPanel apiBaseUrl={API_BASE_URL} bearerToken={DEV_BEARER_TOKEN} />
            <MonitorPanel apiBaseUrl={API_BASE_URL} bearerToken={DEV_BEARER_TOKEN} />
            <AlertInbox
              apiBaseUrl={API_BASE_URL}
              bearerToken={DEV_BEARER_TOKEN}
              onOpenInvestigation={(newInvestigationId) => {
                sessionStorage.setItem("ospreyflow.investigationId", newInvestigationId);
                setInvestigationId(newInvestigationId);
                setView("graph");
              }}
            />
          </div>
        )}
        {view !== "ingest" && view !== "dossier" && view !== "watches" && (
        <div style={{ flex: 1, position: "relative" }}>
          {view === "graph" && (
            <GlassCanvas
              ref={glassCanvasRef}
              graph={workingSetRef.current.graph}
              store={workingSetRef.current.store}
              ontology={ontology}
              edgeTypes={edgeTypes}
              investigationId={investigationId}
              apiBaseUrl={API_BASE_URL}
              bearerToken={DEV_BEARER_TOKEN}
              dimmedNodeIds={dimming.dimmedNodeIds}
              communityHulls={communityHulls}
              onSelectionChange={(nodeIds) => {
                const first = nodeIds[0];
                const graph = workingSetRef.current.graph;
                setSelectedNode(
                  first && graph.hasNode(first)
                    ? graph.getNodeAttribute(first, "data")
                    : null,
                );
              }}
              onViewMessages={(nodeId) => {
                setDossierNodeId(nodeId);
                setView("dossier");
              }}
            />
          )}
          {view === "map" &&
            mapConfig &&
            (() => {
              const provider = defaultProvider(mapConfig);
              if (!provider) {
                return (
                  <div
                    style={{
                      padding: "var(--sp-24)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    No default basemap provider is configured.
                  </div>
                );
              }
              return (
                <>
                  <MapView
                    graph={workingSetRef.current.graph}
                    provider={provider}
                    nodeCoordinates={nodeCoordinates}
                    geoBins={geoBins}
                    snailTrail={revealedSightings}
                    apiBaseUrl={API_BASE_URL}
                    bearerToken={DEV_BEARER_TOKEN}
                    onMapReady={setLiveMap}
                    onNodeClick={(nodeId) => {
                      // A3's "select the hotspot cells" — clicking a
                      // grid-cell Location toggles it in/out of the
                      // cross-filter's node selection (multi-select, since
                      // A3 selects several cells at once).
                      const current = crossFilterStore.store.getState().selectedNodeIds ?? [];
                      const next = current.includes(nodeId)
                        ? current.filter((id) => id !== nodeId)
                        : [...current, nodeId];
                      crossFilterStore.store
                        .getState()
                        .setSelectedNodeIds(next.length > 0 ? next : null);
                      void crossFilterStore.refresh(workingSetRef.current.graph.nodes());
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      top: "var(--sp-8)",
                      left: "var(--sp-8)",
                      width: 240,
                      height: 220,
                      background: "var(--surface-panel)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--r-panel)",
                      overflow: "hidden",
                    }}
                  >
                    <HotspotHistogram
                      apiBaseUrl={API_BASE_URL}
                      bearerToken={DEV_BEARER_TOKEN}
                      investigationScope={investigationId}
                      crossFilterStore={crossFilterStore}
                      getNodeIds={() => workingSetRef.current.graph.nodes()}
                    />
                  </div>
                  {siteWizardOpen && (
                    <SiteCalibrationWizard
                      apiBaseUrl={API_BASE_URL}
                      bearerToken={DEV_BEARER_TOKEN}
                      investigationId={investigationId}
                      map={liveMap}
                      onClose={() => setSiteWizardOpen(false)}
                    />
                  )}
                  {boundaryToolOpen && (
                    <BoundaryFilterTool
                      map={liveMap}
                      crossFilterStore={crossFilterStore}
                      nodeCoordinates={nodeCoordinates}
                      getNodeIds={() => workingSetRef.current.graph.nodes()}
                      onClose={() => setBoundaryToolOpen(false)}
                    />
                  )}
                </>
              );
            })()}
        </div>
        )}
        {view !== "ingest" && view !== "dossier" && view !== "watches" && (
        <div
          style={{
            width: 320,
            borderLeft: "1px solid var(--border-subtle)",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          <Inspector
            node={selectedNode}
            assessment={{
              apiBaseUrl: API_BASE_URL,
              bearerToken: DEV_BEARER_TOKEN,
              investigationId,
              workingSetGraph: workingSetRef.current.graph,
              onHighlightNodes: (nodeIds) => glassCanvasRef.current?.highlightNodes(nodeIds),
            }}
          />
          {view === "graph" && (
            <MetricsPanel
              apiBaseUrl={API_BASE_URL}
              bearerToken={DEV_BEARER_TOKEN}
              investigationId={investigationId}
              graph={workingSetRef.current.graph}
              onFocusNode={(nodeId) => glassCanvasRef.current?.focusOnNode(nodeId)}
              onCommunitiesChange={setCommunities}
            />
          )}
          {view === "graph" && ontologySchema && (
            <QueryBuilderPanel
              apiBaseUrl={API_BASE_URL}
              bearerToken={DEV_BEARER_TOKEN}
              schema={ontologySchema}
            />
          )}
        </div>
        )}
      </div>
      {view !== "ingest" && view !== "dossier" && view !== "watches" && (
      <div
        style={{
          height: 252,
          borderTop: "1px solid var(--border-subtle)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* B16's own cross-case overlay trigger — this build has no
            cross-investigation picker anywhere yet, so a directly-entered
            investigation id is this stage's own real, minimal input, not
            a placeholder for a picker that doesn't exist. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-8)",
            padding: "var(--sp-4) var(--sp-8)",
          }}
        >
          <label htmlFor="cross-case-scope" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            Overlay investigation
          </label>
          <input
            id="cross-case-scope"
            type="text"
            aria-label="Cross-case overlay investigation id"
            placeholder="investigation id"
            value={crossCaseScope}
            onChange={(e) => setCrossCaseScope(e.target.value)}
            style={{ width: 200 }}
          />
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <Timeline
            apiBaseUrl={API_BASE_URL}
            bearerToken={DEV_BEARER_TOKEN}
            investigationScope={investigationId}
            crossFilterStore={crossFilterStore}
            getNodeIds={() => workingSetRef.current.graph.nodes()}
            crossCaseInvestigationScope={crossCaseScope || undefined}
            onPlaybackFractionChange={setPlaybackFraction}
          />
        </div>
      </div>
      )}
      {view !== "ingest" && view !== "dossier" && view !== "watches" && (
      <StatusBar
        nodeCount={counts.nodes}
        edgeCount={counts.edges}
        dimmedCount={dimming.dimmedCount}
        filteredCount={counts.filteredCount}
      />
      )}
      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        investigationId={investigationId}
        apiBaseUrl={API_BASE_URL}
        bearerToken={DEV_BEARER_TOKEN}
        onRestored={(snapshot) =>
          workingSetRef.current.store.getState().applyDelta(snapshot)
        }
      />
      <ExportPanel
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        apiBaseUrl={API_BASE_URL}
        bearerToken={DEV_BEARER_TOKEN}
        investigationId={investigationId}
        graph={workingSetRef.current.graph}
      />
      {toast && (
        <div style={{ position: "fixed", bottom: 16, right: 16 }}>
          <Toast message={toast} />
        </div>
      )}
    </div>
  );
}
