import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  Edge,
  EdgeTypeDef,
  GeoBin,
  Node,
  OntologySchema,
  PublicMapConfig,
  Sighting,
} from "../../../packages/schemas/generated";
import { fetchGeoBins, fetchSightings } from "./analytics/api";
import {
  clearRedirectCallbackParams,
  completeSignInFromRedirect,
  displayPrincipalFromUser,
  getUserManager,
  isSignInRedirectCallback,
  signIn,
  signOut,
  type DisplayPrincipal,
} from "./auth/userManager";
import { clearHandoff, readHandoff } from "./auth/launcherHandoff";
import { installUnauthorisedWatch } from "./auth/unauthorised";
import { SignInScreen } from "./auth/SignInScreen";
import { GlassCanvas, type GlassCanvasHandle } from "./canvas/GlassCanvas";
import { linkTypeName } from "./canvas/linkLabel";
import { DocumentReader } from "./reader/DocumentReader";
import type { DocumentReaderView } from "./reader/readerApi";
import { displayValue } from "./search/searchOptions";
import { listJudgements } from "./assessment/api";
import { judgementCountsByNode } from "./assessment/judgementCounts";
import {
  buildEventFilter,
  createCrossFilterStore,
  type CrossFilterStore,
  type CrossFilterStoreState,
} from "./crossfilter/store";
import { AccountMenu } from "./auth/AccountMenu";
import { ThemeToggle } from "./theme/ThemeToggle";
import { ClassificationStrip, highestMarking } from "./shell/ClassificationStrip";
import { LeftRail } from "./shell/LeftRail";
import { Drawer } from "./design/primitives/Drawer";
import { TopBar } from "./shell/TopBar";
import { fetchHandlingScheme, type HandlingScheme } from "./ingest/api";
import { Button } from "./design/primitives/Button";
import { Toast } from "./design/primitives/Toast";
import { Dossier } from "./dossier/Dossier";
import { ExportPanel } from "./export/ExportPanel";
import { HistoryPanel } from "./history/HistoryPanel";
import { Inspector } from "./inspector/Inspector";
import {
  INVESTIGATION_ID_SESSION_KEY,
  initialInvestigationId,
  investigationIdFromSession,
} from "./investigation/investigationId";
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
import { fetchCaseLinkTypes, type CaseLinkTypes } from "./linktypes/linkTypesApi";
import { ProposedTypes } from "./linktypes/ProposedTypes";
import { GlobalSearch } from "./search/GlobalSearch";
import { drawSearchResult } from "./search/drawSearchResult";
import { BoundaryFilterTool } from "./map/BoundaryFilterTool";
import { IngestStudio } from "./ingest/IngestStudio";
import { CasePicker } from "./investigation/CasePicker";
import { CaseSwitcher } from "./investigation/CaseSwitcher";
import { CaseTabs } from "./investigation/CaseTabs";
import { CaseDatasets } from "./investigation/CaseDatasets";
import { openCase } from "./investigation/cases";
import { QuestionsPanel } from "./questions/QuestionsPanel";
import { ExplorePanel } from "./explore/ExplorePanel";
import type { BusyDay, RankedLink } from "./explore/exploreApi";
import { SiteCalibrationWizard } from "./site/SiteCalibrationWizard";
import { StatusBar } from "./statusbar/StatusBar";
import { emergence, type FirstSeen } from "./crossfilter/emergence";
import type { WorkingSetDelta } from "./workingset/models";
import { NO_FILTER, filterDimming, type MetricFilter } from "./metrics/filters";
import { BottomPanelFrame, SidePanelFrame } from "./layout/PanelFrames";
import { SidePanelStack } from "./layout/SidePanelStack";
import { Timeline } from "./timeline/Timeline";
import { AlertInbox } from "./watches/AlertInbox";
import { HotlistPanel } from "./watches/HotlistPanel";
import { MonitorPanel } from "./watches/MonitorPanel";
import {
  connectDeltaClient,
  type DeltaClient,
  type SocketLike,
} from "./workingset/deltaClient";
import { createWorkingSet } from "./workingset/store";

// **An empty base URL means same-origin, and that is what a rendered
// deployment builds with** (05_DEPLOYMENT.md §2.6 item 1, owner's decision
// of 25 September 2026). The workspace image's own nginx proxies /v1 to
// the Conduit, so every request below is a relative path and the bundle
// carries no address at all. `??` rather than `||` is load-bearing here:
// an empty string is not nullish, so `VITE_API_BASE_URL=""` survives as
// "" instead of falling back to the development default.
//
// `npm run dev` sets nothing and keeps the localhost default, because Vite
// serves the Glass on 5173 with no proxy in front of it.
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// `06_DECISIONS.md` ADR-050: "the VITE_DEV_BEARER_TOKEN path survives only for `npm run dev`."
// `import.meta.env.DEV` is Vite's own `command === "serve"` flag — `false` for every production
// build, so this branch is dead code (and the variable read below moot) in anything
// `vite.config.ts`'s own build-time fence would have let through. There is no Keycloak in
// `deploy/compose/dev.yaml`'s lightweight dev stack (`tools/mint_dev_token.py` mints against a
// throwaway keypair instead), so this path — not the real OIDC flow below — is what `make dev-up`
// and `npm run dev` actually exercise.
const DEV_MODE_BEARER_TOKEN = import.meta.env.DEV
  ? (import.meta.env.VITE_DEV_BEARER_TOKEN ?? "")
  : "";

/** The origin to open the delta WebSocket against.
 *
 * `API_BASE_URL.replace(/^http/, "ws")` produces `""` when the base is
 * empty, leaving a relative `"/v1/…"` for the `WebSocket` constructor.
 * Modern browsers do resolve that against the document's base URL and
 * rewrite http→ws, but that behaviour arrived in the HTML standard well
 * after this API was widely deployed, and a silent failure here is a
 * working set that simply stops updating. Deriving the origin explicitly
 * costs one line and depends on nothing but `window.location`.
 */
function websocketOrigin(apiBaseUrl: string): string {
  if (apiBaseUrl) return apiBaseUrl.replace(/^http/, "ws");
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss:" : "ws:"}//${host}`;
}

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

// Precedence logic (URL param → sessionStorage → create new) lives in
// `investigation/investigationId.ts`, not here — see that module's own docstring.

export function App() {
  const workingSetRef = useRef(createWorkingSet());
  const glassCanvasRef = useRef<GlassCanvasHandle>(null);
  const [groupedCount, setGroupedCount] = useState(0);
  // How many judgements rest on each node, drawn as a small count beside it (ADR-070).
  const [judgementCounts, setJudgementCounts] = useState<ReadonlyMap<string, number>>(new Map());

  // `06_DECISIONS.md` ADR-050 — sign-in. `bearerToken` is the one value every child component
  // already took as a prop before this stage; only its *source* changes, from the dev-only
  // constant to the real access token this state holds once the analyst has signed in.
  const isDevBypass = Boolean(DEV_MODE_BEARER_TOKEN);
  const [bearerToken, setBearerToken] = useState<string>(DEV_MODE_BEARER_TOKEN);
  const [principal, setPrincipal] = useState<DisplayPrincipal | null>(null);
  // `null` until the very first bootstrap effect below has run once — distinguishes "still
  // checking whether this load is a redirect callback" from "checked, and there is no session",
  // which is the difference between showing nothing for one frame and showing the sign-in screen
  // prematurely.
  const [authChecked, setAuthChecked] = useState(isDevBypass);
  // `00_ARCHITECTURE.md` §1.3's own distinction, carried to the Glass: shown on the sign-in
  // screen only when there is something to say — a refused token, a failed silent renewal, or a
  // sign-in that could not complete. `null` on a plain first, unauthenticated load.
  const [signInReason, setSignInReason] = useState<string | null>(null);
  // What the launcher said when it opened this page (`auth/launcherHandoff.ts`): carry the sign-in
  // on without a click (the identity provider already knows the person), and open the Ingest tab
  // when the Ingest Studio tile was the one pressed. Read once. Grants nothing.
  const [handoff] = useState(() => readHandoff(window.location.search, sessionStorage));
  const autoSignInStartedRef = useRef(false);
  // Distinguishes "this token was just refused outright" (wrong audience, wrong claims — show the
  // reason, do not retry) from "this token merely expired mid-session" (retry silently, preserving
  // state) — both surface as a 401 on the same bootstrap call and are otherwise indistinguishable.
  const hasResolvedAPrincipalOnceRef = useRef(isDevBypass);

  useEffect(() => {
    if (isDevBypass) return;
    let cancelled = false;

    async function bootstrap() {
      const params = new URLSearchParams(window.location.search);
      if (params.has("error")) {
        const reason =
          params.get("error_description") ??
          params.get("error") ??
          "sign-in failed";
        clearRedirectCallbackParams();
        if (!cancelled) {
          setSignInReason(
            reason === "login_required"
              ? "Your session has ended. Sign in again to continue — your place in the " +
                  "investigation has been saved."
              : `Your sign-in could not be completed: ${reason}.`,
          );
          setAuthChecked(true);
        }
        return;
      }
      let signedIn = false;
      if (isSignInRedirectCallback()) {
        try {
          const user = await completeSignInFromRedirect();
          clearRedirectCallbackParams();
          if (cancelled) return;
          setBearerToken(user.access_token);
          setPrincipal(displayPrincipalFromUser(user));
          restoreViewStateAfterReauth();
          signedIn = true;
          clearHandoff(sessionStorage);
        } catch {
          clearRedirectCallbackParams();
          if (!cancelled)
            setSignInReason("Your sign-in could not be completed. Try again.");
        }
      }
      // Arrived from the launcher and not signed in: start the sign-in now rather than show a
      // screen whose only content is a button. Once per load (`autoSignInStartedRef` survives
      // React's development double-run), never after a refusal (that returned above, with an
      // `error` parameter), and never after a completed or failed callback. If it cannot be
      // started, the screen appears with a plain sentence and its button still works.
      if (!cancelled && !signedIn && handoff.autoSignIn && !autoSignInStartedRef.current) {
        autoSignInStartedRef.current = true;
        try {
          await signIn();
          return;
        } catch {
          if (!cancelled)
            setSignInReason(
              "Sign-in could not be started automatically. Press Sign in to try again.",
            );
        }
      }
      if (!cancelled) setAuthChecked(true);
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, at mount, deliberately.
  }, []);

  /** ADR-050's Decision section: "the Glass preserves only the investigation id, the current
   * selection and the view state… re-fetches the working set… before restoring the view." Called
   * once a fresh token is obtained, whether from completing a redirect callback above or from the
   * silent `prompt=none` round `reauthenticateAfterExpiry` below triggers. Restoring the
   * investigation id here only re-primes what `initialInvestigationId()` already reads from
   * `sessionStorage` on the *next* mount — this component does not remount on a same-page state
   * change, so nothing further is needed for it. Selection/view-state restoration is left as a
   * disclosed, not-yet-built gap: `07_BUILD_PLAN.md`'s Stage 2c entry records it honestly rather
   * than claiming it silently.
   */
  function restoreViewStateAfterReauth(): void {
    hasResolvedAPrincipalOnceRef.current = false;
  }

  const unauthenticatedHandledRef = useRef(false);
  const bearerTokenRef = useRef(bearerToken);
  bearerTokenRef.current = bearerToken;
  // A new token is a new sign-in: a refusal of *it* is worth reacting to again.
  useEffect(() => {
    if (bearerToken) unauthenticatedHandledRef.current = false;
  }, [bearerToken]);

  /** A 401 on the very first authenticated call after sign-in means the token itself was refused
   * (wrong audience, a claim the realm never mapped) — retrying it against the same identity-
   * provider session would only fetch the identical bad token again. A 401 on any later call means
   * the token merely expired during use, and ADR-050's own silent `prompt=none` round is the right
   * response. The two need different reactions, and a bare 401 cannot tell them apart on its own —
   * only "has this session ever produced a usable token" can. */
  const handleUnauthenticatedResponse = useCallback((): void => {
    if (isDevBypass) return;
    // Once per sign-in: several calls refused together must start one re-sign-in, not several.
    if (unauthenticatedHandledRef.current) return;
    unauthenticatedHandledRef.current = true;
    if (!hasResolvedAPrincipalOnceRef.current) {
      setBearerToken("");
      setPrincipal(null);
      setSignInReason(
        "Your sign-in could not be used to reach the workspace. Check with your " +
          "administrator that this deployment's identity provider is configured correctly.",
      );
      return;
    }
    setBearerToken("");
    setPrincipal(null);
    void getUserManager().signinRedirect({ prompt: "none" });
  }, [isDevBypass]);

  // A 401 from the Conduit on *any* call carrying the signed-in token means the sign-in has gone
  // stale, whichever screen made the call (3 October 2026: the Ingest Studio and the case menu
  // showed raw 401s after the identity provider was restarted, because only the Glass's own calls
  // were wired to the handler above). Watching `fetch` once covers every screen, present and future.
  useEffect(() => {
    if (isDevBypass) return;
    return installUnauthorisedWatch({
      apiBaseUrl: API_BASE_URL,
      getToken: () => bearerTokenRef.current,
      onUnauthorised: handleUnauthenticatedResponse,
    });
  }, [isDevBypass, handleUnauthenticatedResponse]);

  // The case picker shown over an open case ("All cases" in the header). It replaces the workspace
  // in the render, it does not unmount `App`, so the sign-in and the per-case state survive.
  const [browsingCases, setBrowsingCases] = useState(false);
  const [investigationId, setInvestigationId] = useState<string | null>(
    initialInvestigationId(),
  );
  // Phase 7 Stage 3: the metrics panel's own "Show community hulls" toggle feeds this, `App.tsx`
  // (not `MetricsPanel` itself) turns it into hull geometry — `MetricsPanel` has no dependency on
  // Sigma/the canvas at all, the same separation `onSelectionChange`/`onViewMessages` already draw
  // between "what happened" and "what the canvas does about it."
  const [communities, setCommunities] = useState<Record<string, string> | null>(
    null,
  );
  const [ontology, setOntology] = useState<OntologyRegistry | null>(null);
  const [ontologyEdgeTypes, setEdgeTypes] = useState<EdgeTypeDef[]>([]);
  // ADR-090: the types a link in this case may take, read from the case: the ontology's, and those
  // analysts proposed in it, its parents or on a link in view, so a proposed type is named and drawn
  // in its own colour, dotted. `null` until read, or when the read fails: the ontology's alone.
  const [caseLinkTypes, setCaseLinkTypes] = useState<CaseLinkTypes | null>(null);
  const [linkTypesRead, setLinkTypesRead] = useState(0);
  const edgeTypes = useMemo(
    () => caseLinkTypes?.definitions ?? ontologyEdgeTypes,
    [caseLinkTypes, ontologyEdgeTypes],
  );
  // The full schema, not only `OntologyRegistry`'s own channel/shape lookup — Phase 7 Stage 4's
  // `QueryBuilderPanel` needs the entity/edge type *names* to populate its own palette and connect
  // controls, which `OntologyRegistry` was never built to expose. Captured from the same `/v1
  // /ontology` fetch `edgeTypes` already comes from, not a third redundant request.
  const [ontologySchema, setOntologySchema] = useState<OntologySchema | null>(
    null,
  );
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  /** ADR-100: an Explore item does what choosing a search result does: draws it and selects it. */
  const pickToStart = (node: Node) => {
    drawSearchResult(workingSetRef.current.store, node, glassCanvasRef.current);
    setSelectedNode(node);
  };
  /** ADR-100 decision 5: a busiest link puts the pair and their link on the canvas. */
  const pickLinkToStart = (link: RankedLink) => {
    const store = workingSetRef.current.store;
    store.getState().applyDelta({
      seq: store.getState().seq,
      op: "add",
      nodes: [link.source, link.target],
      edges: [link.edge],
    });
    setSelectedNode(link.source);
  };
  /** ADR-100 Amendment 7: what a starter question put in the case's working set, drawn. */
  const applyStarterDelta = (delta: WorkingSetDelta) => {
    workingSetRef.current.store.getState().applyDelta(delta);
  };
  const [timelineOpenSignal, setTimelineOpenSignal] = useState(0);
  /** ADR-100 decision 5: a busiest day becomes the timeline's window, and the timeline opens. */
  const pickDay = (day: BusyDay) => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter) return;
    crossFilter.store.getState().setWindow({ validFrom: day.start, validTo: day.end });
    const graph = workingSetRef.current.graph;
    void crossFilter.refresh(graph.nodes(), graph.edges());
    setTimelineOpenSignal((n) => n + 1);
  };
  const [selectedLink, setSelectedLink] = useState<Edge | null>(null);
  // ADR-080: the link menu's *Add a note* and *Change link…* count these up to bring that part of
  // the Inspector forward.
  const [linkNoteSignal, setLinkNoteSignal] = useState(0);
  const [linkChangeSignal, setLinkChangeSignal] = useState(0);
  const [linkEventsSignal, setLinkEventsSignal] = useState(0);
  const [linkHistorySignal, setLinkHistorySignal] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  // ADR-097 Amendment 1: the case and its branches, reached from the rail.
  const [casesOpen, setCasesOpen] = useState(false);
  // ADR-098 decision 4: the case's questions to the model, open at once in a case branched for them.
  const [questionsOpen, setQuestionsOpen] = useState(handoff.view === "questions");
  // ADR-100: where to start in a case's data, from the rail (and over an empty canvas).
  const [exploreOpen, setExploreOpen] = useState(false);
  // ADR-097 step 1 (review item 16): the deployment's classifications, lowest first, for the strip.
  const [classificationOrder, setClassificationOrder] = useState<readonly string[]>([]);
  // ADR-102: the scheme, so a link's handling can be changed on purpose.
  const [handlingScheme, setHandlingScheme] = useState<HandlingScheme | undefined>(undefined);
  const [proposedTypesOpen, setProposedTypesOpen] = useState(false);
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
  // The highest classification among the nodes and links in the view (ADR-097 Amendment 1), read
  // again whenever the view's counts change.
  const marking = useMemo(() => {
    const graph = workingSetRef.current?.graph;
    const found: string[] = [];
    graph?.forEachNode((_id, attributes) => {
      const c = (attributes as { data?: { handling?: { classification?: string } } }).data?.handling?.classification;
      if (c) found.push(c);
    });
    graph?.forEachEdge((_id, attributes) => {
      const c = (attributes as { data?: { handling?: { classification?: string } } }).data?.handling?.classification;
      if (c) found.push(c);
    });
    return highestMarking(found, classificationOrder);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counts, classificationOrder]);

  const [view, setView] = useState<
    "graph" | "map" | "ingest" | "dossier" | "watches"
  >(handoff.view === "ingest" ? "ingest" : "graph");
  // Which application is open, and (so the switch can go back to it) the Glass view last open.
  const app = view === "ingest" ? "ingest" : "glass";
  const lastGlassView = useRef<"graph" | "map" | "dossier" | "watches">("graph");
  if (view !== "ingest") lastGlassView.current = view;
  const [dossierNodeId, setDossierNodeId] = useState<string | null>(null);
  // ADR-092: the Document open in the full-screen reader, if any.
  const [readerDocumentId, setReaderDocumentId] = useState<string | null>(null);
  // ADR-092 Amendment 3: an email opened from the Inspector, shown until its Document exists.
  const [readerFallback, setReaderFallback] = useState<DocumentReaderView | undefined>(undefined);
  // ADR-093: every node selected on the canvas, for the Inspector's list.
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [mapConfig, setMapConfig] = useState<PublicMapConfig | null>(null);
  const [siteWizardOpen, setSiteWizardOpen] = useState(false);
  const [boundaryToolOpen, setBoundaryToolOpen] = useState(false);
  const [liveMap, setLiveMap] = useState<MapLibreMap | null>(null);
  // Constructed once `investigationId` **and** `bearerToken` are both known — `investigationScope`
  // is frozen into the store at creation (`crossfilter/store.ts`), and `investigationId` only ever
  // moves from `null` to a real id once per session, never changes again, so a lazy ref assignment
  // during render (rather than an effect) is safe here. Gating on `bearerToken` too matters now
  // that it can start empty (unauthenticated) and arrive later: `initialInvestigationId()` reads
  // from the URL/sessionStorage independently of sign-in, so `investigationId` alone is not
  // evidence that a real request should be made yet.
  //
  // **Known, disclosed limitation** (`07_BUILD_PLAN.md`'s Stage 2c entry): the token frozen in here
  // at creation does not itself rotate if `bearerToken` later changes (a mid-session silent
  // renewal) — every other consumer below re-reads `bearerToken` as a plain prop on each render,
  // so only this one, already-existing "construct once" pattern carries the gap forward.
  const crossFilterRef = useRef<CrossFilterStore | null>(null);
  if (investigationId && bearerToken && !crossFilterRef.current) {
    crossFilterRef.current = createCrossFilterStore(
      API_BASE_URL,
      bearerToken,
      investigationId,
    );
  }
  const [dimming, setDimming] = useState<{
    dimmedNodeIds: ReadonlySet<string>;
    dimmedEdgeIds: ReadonlySet<string>;
    firstSeen: FirstSeen | null;
    dimmedCount: number;
  }>({
    dimmedNodeIds: EMPTY_DIMMED_NODE_IDS,
    dimmedEdgeIds: EMPTY_DIMMED_NODE_IDS,
    firstSeen: null,
    dimmedCount: 0,
  });
  const [nodeCoordinates, setNodeCoordinates] = useState(
    EMPTY_NODE_COORDINATES,
  );
  const [geoBins, setGeoBins] = useState<readonly GeoBin[]>(EMPTY_GEO_BINS);

  useEffect(() => {
    // `06_DECISIONS.md` ADR-050's tests-owed list: "an unauthenticated load presents the sign-in…
    // and issues no /v1 call." `bearerToken` is `""` until sign-in completes (or the dev bypass
    // supplies it), and every effect below that reaches `/v1` is gated on it for exactly that
    // reason — this one first, since it is the earliest bootstrap call in the component.
    if (!bearerToken) return;
    void fetchOntologyRegistry(API_BASE_URL, bearerToken).then((registry) => {
      setOntology(registry);
    });
    void fetch(`${API_BASE_URL}/v1/ontology`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      .then((r) => {
        if (r.status === 401) {
          handleUnauthenticatedResponse();
          return null;
        }
        hasResolvedAPrincipalOnceRef.current = true;
        return r.json();
      })
      .then((schema: OntologySchema | null) => {
        if (!schema) return;
        setEdgeTypes(schema.edge_types);
        setOntologySchema(schema);
      });
    void fetchMapConfig(API_BASE_URL, bearerToken).then(setMapConfig);
    fetchHandlingScheme(API_BASE_URL, bearerToken)
      .then((scheme) => {
        setClassificationOrder(scheme.classification ?? []);
        setHandlingScheme(scheme);
      })
      .catch(() => setClassificationOrder([]));
  }, [bearerToken, handleUnauthenticatedResponse]);

  useEffect(() => {
    if (!bearerToken || !investigationId) return;
    let current = true;
    fetchCaseLinkTypes(API_BASE_URL, bearerToken, investigationId)
      .then((types) => {
        if (current) setCaseLinkTypes(types);
      })
      .catch(() => {
        if (current) setCaseLinkTypes(null);
      });
    return () => {
      current = false;
    };
  }, [bearerToken, investigationId, linkTypesRead]);

  useEffect(() => {
    // Persisting an already-resolved id makes no network call and must run regardless of auth
    // state — found running the real exit test: gating this on `bearerToken` too (like the POST
    // fallback below, which genuinely needs it) meant a `?investigation=` URL param was never
    // written to `sessionStorage` before the sign-in redirect navigated away, so the round trip
    // came back with no memory of it and silently created a second, empty investigation instead
    // of opening the one the URL named. `spec/02_GLASS_FRONTEND.md` §2.1's own "written back to
    // sessionStorage immediately" is unconditional for exactly this reason.
    if (investigationId) {
      sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, investigationId);
      return;
    }
    // No case is created here any more (ADR-052, owner's ruling of 29 September 2026): with no
    // case chosen the Glass shows the case picker, and a case is only ever created by naming one.
  }, [investigationId]);

  // The count of judgements beside each node (ADR-070): fetched when the case opens, then kept
  // current by the Judgements tab each time it reloads the list. A failure leaves no badges; it
  // never blocks the canvas.
  useEffect(() => {
    if (!investigationId || !bearerToken) {
      setJudgementCounts(new Map());
      return;
    }
    let cancelled = false;
    listJudgements(API_BASE_URL, bearerToken, investigationId)
      .then((judgements) => {
        if (!cancelled) setJudgementCounts(judgementCountsByNode(judgements));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [investigationId, bearerToken]);

  useEffect(() => {
    if (!investigationId || !bearerToken) return;
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
      void crossFilterRef.current?.refresh(workingSet.graph.nodes(), workingSet.graph.edges());
      // Likewise, a delta can add a `Location` node the map has never
      // plotted — re-resolve every working-set `Location`'s geometry_ref
      // whenever membership changes. A no-op fast path when the working
      // set has no `Location` nodes yet (`resolveNodeCoordinates`'s own
      // early return).
      void resolveNodeCoordinates(
        API_BASE_URL,
        bearerToken,
        workingSet.graph,
      ).then(setNodeCoordinates);
    });

    const wsUrl = websocketOrigin(API_BASE_URL);
    // A browser's native `WebSocket` cannot set an `Authorization` header at all.
    // `06_DECISIONS.md` ADR-050 objection 8, built: rather than a bearer token in this URL
    // (Checkpoint 2's own fallback, and a real log-exposure gap — see `services/api/ws_ticket.py`'s
    // own module docstring), this fetches a short-lived, single-use `?ticket=` from
    // `POST /v1/ws-ticket` first, authenticated the ordinary way, and opens the socket with that
    // instead. A bearer token in this URL is refused outright by `_authenticate_websocket`, not
    // merely no longer preferred, so there is no fallback path left to fall back to.
    //
    // `bearerToken` in the dependency array below is `06_DECISIONS.md` ADR-050's own "the delta
    // WebSocket authenticates on connect and on every reconnect": a token rotation (the silent
    // `prompt=none` round `handleUnauthenticatedResponse` triggers) tears this effect down and
    // re-establishes the connection with a freshly minted ticket, rather than an already-open
    // socket continuing to carry the one it dialled with.
    let cancelled = false;
    let client: DeltaClient | null = null;
    void fetch(`${API_BASE_URL}/v1/ws-ticket`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      .then((r) => {
        if (r.status === 401) {
          handleUnauthenticatedResponse();
          return null;
        }
        return r.json();
      })
      .then((body: { ticket: string } | null) => {
        if (!body || cancelled) return;
        client = connectDeltaClient(
          () =>
            new WebSocket(
              `${wsUrl}/v1/investigations/${investigationId}/stream?ticket=${encodeURIComponent(body.ticket)}`,
            ) as unknown as SocketLike,
          { onDelta: (delta) => workingSet.store.getState().applyDelta(delta) },
        );
      });
    return () => {
      cancelled = true;
      client?.close();
      unsubscribe();
    };
  }, [investigationId, bearerToken, handleUnauthenticatedResponse]);

  useEffect(() => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter) return;
    const unsubscribe = crossFilter.store.subscribe((state) => {
      setDimming({
        dimmedNodeIds: state.dimmedNodeIds,
        dimmedEdgeIds: state.dimmedEdgeIds,
        firstSeen: state.firstSeen,
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
      const filter = buildEventFilter(
        scope,
        state.window,
        state.selectedNodeIds,
      );
      const bins = await fetchGeoBins(API_BASE_URL, bearerToken, {
        filter,
        precision: GEO_BIN_PRECISION,
      });
      setGeoBins(bins);
    }
    let lastWindow = crossFilter.store.getState().window;
    let lastSelected = crossFilter.store.getState().selectedNodeIds;
    void refresh(crossFilter.store.getState());
    const unsubscribe = crossFilter.store.subscribe((state) => {
      if (state.window === lastWindow && state.selectedNodeIds === lastSelected)
        return;
      lastWindow = state.window;
      lastSelected = state.selectedNodeIds;
      void refresh(state);
    });
    return () => unsubscribe();
  }, [investigationId, bearerToken]);

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
      void fetchSightings(API_BASE_URL, bearerToken, {
        filter: buildEventFilter(scope, window, [entityId]),
      }).then((result) => {
        if (!cancelled) setSightings(result);
      });
    }
    refresh(crossFilter.store.getState().window);
    const unsubscribe = crossFilter.store.subscribe((state) =>
      refresh(state.window),
    );
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [investigationId, selectedNode, bearerToken]);

  // The revealed prefix of `sightings` at the current playback position —
  // recomputed on every animation frame (`playbackFraction` changes), the
  // real content change B18's own "animates under playback" names, not a
  // CSS trick layered over a static list.
  // ADR-087: under playback the graph emerges. Until the clock runs (fraction 0) or with no brush,
  // the store's own dimming stands; while it runs, each node and link stays dimmed until the
  // playhead passes its first event in the window.
  const playbackDimming = useMemo(() => {
    const window = crossFilterRef.current?.store.getState().window;
    if (!window || dimming.firstSeen === null || playbackFraction <= 0) return null;
    const graph = workingSetRef.current.graph;
    return emergence(
      dimming.firstSeen,
      instantAtFraction(window, playbackFraction),
      graph.nodes(),
      graph.edges(),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dimming.firstSeen, playbackFraction, counts]);
  // ADR-088: the Metrics panel's own filters dim too, on top of the timeline's.
  const [metricFilter, setMetricFilter] = useState<MetricFilter>(NO_FILTER);
  const metricDimming = useMemo(() => {
    const graph = workingSetRef.current.graph;
    const edges = graph.mapEdges((id, attrs, source, target) => ({
      id,
      source,
      target,
      weight: attrs.data.weight ?? 0,
    }));
    return filterDimming(graph.nodes(), edges, metricFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metricFilter, counts]);
  const timelineNodeDimming = playbackDimming?.dimmedNodeIds ?? dimming.dimmedNodeIds;
  const timelineEdgeDimming = playbackDimming?.dimmedEdgeIds ?? dimming.dimmedEdgeIds;
  const dimmedNodeIds = useMemo(
    () => new Set([...timelineNodeDimming, ...metricDimming.dimmedNodeIds]),
    [timelineNodeDimming, metricDimming],
  );
  const dimmedEdgeIds = useMemo(
    () => new Set([...timelineEdgeDimming, ...metricDimming.dimmedEdgeIds]),
    [timelineEdgeDimming, metricDimming],
  );

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
    () =>
      communities
        ? computeCommunityHulls(workingSetRef.current.graph, communities)
        : undefined,
    [communities],
  );

  // `06_DECISIONS.md` ADR-050's tests-owed list: "an unauthenticated load presents the sign-in,
  // not an error page and not an empty workspace." Checked before the "not ready yet" branch below
  // — an unauthenticated caller is never "still loading", it has a definite answer already.
  if (!isDevBypass && authChecked && !bearerToken) {
    return (
      <SignInScreen
        reason={signInReason}
        intent={handoff.view}
        onSignIn={() => void signIn()}
      />
    );
  }

  if ((!investigationId || browsingCases) && (isDevBypass || bearerToken)) {
    return (
      <CasePicker
        openCaseId={investigationId}
        onClose={investigationId ? () => setBrowsingCases(false) : undefined}
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        lastCaseId={investigationIdFromSession()}
        isAdministrator={principal?.roles?.includes("osprey-admin") ?? false}
        onOpen={(id) => openCase(id)}
      />
    );
  }

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
      {/* ADR-097 step 1 (design review item 16): the protective marking of what is on screen. */}
      <ClassificationStrip marking={marking} />
      <TopBar
        app={app}
        caseSwitcher={
          <CaseSwitcher
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            currentId={investigationId}
            onBrowse={() => setBrowsingCases(true)}
            onOpen={(id) => openCase(id, view === "ingest" ? "ingest" : undefined)}
          />
        }
        search={
          app === "glass" ? (
            <GlobalSearch
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationId={investigationId}
              entityTypes={ontologySchema?.entity_types.map((e) => e.name) ?? []}
              screenNodes={() => {
                const graph = workingSetRef.current.graph;
                return graph.nodes().map((id) => graph.getNodeAttribute(id, "data"));
              }}
              onSelect={(node) => {
                drawSearchResult(
                  workingSetRef.current.store,
                  node,
                  glassCanvasRef.current,
                );
                setSelectedNode(node);
              }}
            />
          ) : undefined
        }
        views={
          app === "glass"
            ? [
                { id: "graph", label: "Graph", pressed: view === "graph", onSelect: () => setView("graph") },
                { id: "map", label: "Map", pressed: view === "map", onSelect: () => setView("map") },
                ...(dossierNodeId
                  ? [{ id: "dossier", label: "Messages", pressed: view === "dossier", onSelect: () => setView("dossier") }]
                  : []),
              ]
            : []
        }
        actions={
          view === "graph" ? (
            // `02_GLASS_FRONTEND.md` §10: the export drawer, for the whole case.
            // ADR-097 step 3: one menu button that opens the export panel, not a pressed toggle.
            <Button aria-haspopup="dialog" aria-expanded={exportOpen} onClick={() => setExportOpen((open) => !open)}>
              Export <span aria-hidden="true">▾</span>
            </Button>
          ) : undefined
        }
        account={
          <>
            {/* ADR-097 step 3: the theme is in the account menu; a button of its own only without one. */}
            {(isDevBypass || !principal) && <ThemeToggle />}
            {!isDevBypass && principal && (
              // `06_DECISIONS.md` ADR-050: the principal's identity and clearance are shown in the
              // chrome, informationally only. ADR-065 folds the subject, unit and Sign out behind one
              // button that keeps the clearance in view. The Glass derives nothing from any of it.
              <AccountMenu principal={principal} onSignOut={() => void signOut()} />
            )}
          </>
        }
      />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      {/* ADR-097 step 1: the places the analyst goes to, on the left rail. */}
      <LeftRail
        items={[
          ...(app === "glass"
            ? [
                { id: "cases", label: "Cases", icon: "cases" as const, onSelect: () => setCasesOpen(true), pressed: casesOpen },
                { id: "watches", label: "Watches", icon: "watches" as const, onSelect: () => setView("watches"), pressed: view === "watches" },
                { id: "history", label: "History", icon: "history" as const, onSelect: () => setHistoryOpen(true), pressed: historyOpen },
                { id: "explore", label: "Explore", icon: "explore" as const, onSelect: () => setExploreOpen(true), pressed: exploreOpen },
                { id: "questions", label: "Questions", icon: "questions" as const, onSelect: () => setQuestionsOpen(true), pressed: questionsOpen },
                ...((principal?.roles?.includes("osprey-admin") ?? false)
                  ? // ADR-090 C3: the relationship types analysts of the administrator's unit proposed.
                    [{ id: "types", label: "Proposed types", icon: "types" as const, onSelect: () => setProposedTypesOpen(true), pressed: proposedTypesOpen }]
                  : []),
                { id: "ingest", label: "Ingest Studio", icon: "ingest" as const, onSelect: () => setView("ingest") },
              ]
            : [
                { id: "investigation", label: "Back to the investigation", icon: "glass" as const, onSelect: () => setView(lastGlassView.current) },
              ]),
        ]}
      />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      {(view === "graph" || view === "map") && (
        // ADR-097 step 1: what belongs to this view alone, docked above it.
        <div role="toolbar" aria-label={view === "graph" ? "Graph view" : "Map view"} className="view-toolbar">
          {view === "graph" && (
            <ResolutionThresholdControl
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationId={investigationId}
              store={workingSetRef.current.store}
              onChangeSummary={setToast}
            />
          )}
          {view === "map" && (
            <>
              <Button aria-pressed={siteWizardOpen} onClick={() => setSiteWizardOpen((open) => !open)}>
                Add site
              </Button>
              <Button aria-pressed={boundaryToolOpen} onClick={() => setBoundaryToolOpen((open) => !open)}>
                Draw boundary
              </Button>
            </>
          )}
        </div>
      )}
      <div style={{ flex: 1, display: "flex", minHeight: 0, position: "relative" }}>
        {readerDocumentId !== null && investigationId && bearerToken && ontology && (
          <DocumentReader
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            documentId={readerDocumentId}
            fallback={readerFallback}
            ontology={ontology}
            labelOf={(id) => {
              const graph = workingSetRef.current.graph;
              return graph.hasNode(id) ? displayValue(graph.getNodeAttribute(id, "data")) : id;
            }}
            onClose={() => {
              setReaderDocumentId(null);
              setReaderFallback(undefined);
              // Back where the analyst was: the canvas, with its focused node, untouched behind.
              document.querySelector<HTMLElement>('[role="application"][aria-label="Network canvas"]')?.focus();
            }}
            onDelta={(delta) => workingSetRef.current.store.getState().applyDelta(delta as WorkingSetDelta)}
          />
        )}
        {view === "ingest" && (
          <IngestStudio
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            onOpenCase={(id) => openCase(id, "ingest")}
          />
        )}
        {view === "dossier" && dossierNodeId && (
          <Dossier
            graph={workingSetRef.current.graph}
            ontology={ontology}
            nodeId={dossierNodeId}
            investigationId={investigationId}
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            onSelectNode={(nodeId) => {
              const graph = workingSetRef.current.graph;
              setSelectedNode(
                graph.hasNode(nodeId)
                  ? graph.getNodeAttribute(nodeId, "data")
                  : null,
              );
              setView("graph");
            }}
          />
        )}
        {view === "watches" && (
          // Owner-only, not investigation-scoped — the same reasoning `/v1/patterns/*` already
          // gives (`patterns/api.ts`'s own module docstring) — so this view, like "ingest" and
          // "dossier", opts out of the investigation-scoped side panel/timeline/status bar below
          // rather than being squeezed into `view === "graph"`'s own 320px column.
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-8)",
              overflowY: "auto",
              padding: "var(--sp-8)",
            }}
          >
            <HotlistPanel apiBaseUrl={API_BASE_URL} bearerToken={bearerToken} investigationId={investigationId} />
            <MonitorPanel apiBaseUrl={API_BASE_URL} bearerToken={bearerToken} investigationId={investigationId} />
            <AlertInbox
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationId={investigationId}
              onOpenInvestigation={(newInvestigationId) => {
                sessionStorage.setItem(
                  INVESTIGATION_ID_SESSION_KEY,
                  newInvestigationId,
                );
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
                entityTypes={ontologySchema?.entity_types}
                investigationId={investigationId}
                apiBaseUrl={API_BASE_URL}
                bearerToken={bearerToken}
                dimmedNodeIds={dimmedNodeIds}
                dimmedEdgeIds={dimmedEdgeIds}
                onGroupedCountChange={setGroupedCount}
                judgementCounts={judgementCounts}
                communityHulls={communityHulls}
                onEdgeSelect={setSelectedLink}
                getEventsWindow={() => crossFilterRef.current?.store.getState().window ?? null}
                onOpenDocument={(id) => {
                  setReaderFallback(undefined);
                  setReaderDocumentId(id);
                }}
                onLinkAction={(_edge, action) => {
                  if (action === "note") setLinkNoteSignal((n) => n + 1);
                  if (action === "change") setLinkChangeSignal((n) => n + 1);
                  if (action === "events") setLinkEventsSignal((n) => n + 1);
                  if (action === "history") setLinkHistorySignal((n) => n + 1);
                }}
                onBranchCreated={(id) => openCase(id)}
                onAskAboutDocuments={(id) => openCase(id, "questions")}
                onSelectionChange={(nodeIds) => {
                  setSelectedNodeIds(nodeIds);
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
            {/* ADR-100: an empty canvas offers where to start, until something is drawn. */}
            {view === "graph" && counts.nodes === 0 && investigationId && (
              <div
                className="explore-overlay"
                style={{
                  position: "absolute",
                  top: "var(--sp-40)",
                  left: "50%",
                  transform: "translateX(-50%)",
                  width: "min(28rem, calc(100% - var(--sp-32)))",
                  maxHeight: "calc(100% - var(--sp-56) - var(--sp-24))",
                  overflowY: "auto",
                  padding: "var(--sp-16)",
                  background: "var(--surface-panel)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--r-overlay)",
                }}
              >
                <h2 style={{ fontSize: "var(--fs-14)", margin: "0 0 var(--sp-8)" }}>Where to start</h2>
                <p style={{ color: "var(--text-secondary)", margin: "0 0 var(--sp-12)", fontSize: "var(--fs-12)" }}>
                  Search above, or start from what this case holds.
                </p>
                <ExplorePanel
                  apiBaseUrl={API_BASE_URL}
                  bearerToken={bearerToken}
                  investigationId={investigationId}
                  edgeTypes={edgeTypes}
                  onPick={pickToStart}
                  onPickLink={pickLinkToStart}
                  onPickDay={pickDay}
                  onApplyDelta={applyStarterDelta}
                />
              </div>
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
                    {/* **The snail trail's own readout — round 13cde.**
                     *
                     * B18's track is a MapLibre GeoJSON source
                     * (`map/MapView.tsx`'s `ospreyflow-snail-trail`), so what
                     * playback changes is pixels and nothing else: a screen
                     * reader is told nothing at all when the trail advances,
                     * and no test at any tier can observe it without
                     * comparing images. Both of those are the same gap.
                     *
                     * `02_GLASS_FRONTEND.md` §2 fixes the status bar's own
                     * four segments, so this is a readout beside the surface
                     * it describes rather than a fifth segment there.
                     * Rendered only when there is a trail to describe —
                     * an empty live region announcing "0 of 0" on every view
                     * would be noise, and `aria-live` is not a place to put
                     * noise. */}
                    {sightings.length > 0 && (
                      <div
                        role="status"
                        aria-live="polite"
                        className="value"
                        style={{
                          padding: "var(--sp-4) var(--sp-16)",
                          color: "var(--text-secondary)",
                          fontSize: "var(--fs-13)",
                        }}
                      >
                        {revealedSightings.length.toLocaleString()} of{" "}
                        {sightings.length.toLocaleString()} sightings revealed
                      </div>
                    )}
                    <MapView
                      graph={workingSetRef.current.graph}
                      provider={provider}
                      nodeCoordinates={nodeCoordinates}
                      geoBins={geoBins}
                      snailTrail={revealedSightings}
                      apiBaseUrl={API_BASE_URL}
                      bearerToken={bearerToken}
                      onMapReady={setLiveMap}
                      onNodeClick={(nodeId) => {
                        // A3's "select the hotspot cells" — clicking a
                        // grid-cell Location toggles it in/out of the
                        // cross-filter's node selection (multi-select, since
                        // A3 selects several cells at once).
                        const current =
                          crossFilterStore.store.getState().selectedNodeIds ??
                          [];
                        const next = current.includes(nodeId)
                          ? current.filter((id) => id !== nodeId)
                          : [...current, nodeId];
                        crossFilterStore.store
                          .getState()
                          .setSelectedNodeIds(next.length > 0 ? next : null);
                        void crossFilterStore.refresh(
                          workingSetRef.current.graph.nodes(),
                        );
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
                        bearerToken={bearerToken}
                        investigationScope={investigationId}
                        crossFilterStore={crossFilterStore}
                        getNodeIds={() => workingSetRef.current.graph.nodes()}
                      />
                    </div>
                    {siteWizardOpen && (
                      <SiteCalibrationWizard
                        apiBaseUrl={API_BASE_URL}
                        bearerToken={bearerToken}
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
          <SidePanelFrame name="Inspector">
            <SidePanelStack
              panels={[
                {
                  id: "inspector" as const,
                  name: "Inspector",
                  content: (
                    <>
                    <Inspector
                      node={selectedNode}
                      // ADR-097 step 1: several selected are shown together (the list of ADR-093
                      // is one of their parts), not the first alone.
                      selection={{
                        nodes: selectedNodeIds
                          .filter((id) => workingSetRef.current.graph.hasNode(id))
                          .map((id) => workingSetRef.current.graph.getNodeAttribute(id, "data")),
                        onCentre: (id) => glassCanvasRef.current?.centreOn(id),
                        onRemove: (id) => glassCanvasRef.current?.deselect(id),
                      }}
                      visualFor={(type) => ontology.visualFor(type)}
                      sharedContacts={
                        ontologySchema
                          ? {
                              apiBaseUrl: API_BASE_URL,
                              bearerToken,
                              investigationId,
                              edgeTypes: ontologySchema.edge_types,
                              onDelta: applyStarterDelta,
                            }
                          : undefined
                      }
                      link={
                        selectedLink
                          ? {
                              edge: selectedLink,
                              source: workingSetRef.current.graph.hasNode(selectedLink.source)
                                ? workingSetRef.current.graph.getNodeAttribute(selectedLink.source, "data")
                                : undefined,
                              target: workingSetRef.current.graph.hasNode(selectedLink.target)
                                ? workingSetRef.current.graph.getNodeAttribute(selectedLink.target, "data")
                                : undefined,
                              directed:
                                edgeTypes.find((t) => t.name === selectedLink.type)?.directed ?? true,
                              typeBasis:
                                edgeTypes.find((t) => t.name === selectedLink.type)?.basis ?? null,
                              typeName: linkTypeName(selectedLink.type, edgeTypes),
                            }
                          : null
                      }
                      linkEditing={{
                        edgeTypes,
                        proposedTypes: caseLinkTypes?.proposed,
                        getEventsWindow: () => crossFilterRef.current?.store.getState().window ?? null,
                        onTypeProposed: () => setLinkTypesRead((n) => n + 1),
                        handlingScheme,
                        onReadFullScreen: (view) => {
                          setReaderFallback(view);
                          setReaderDocumentId(view.document_id);
                        },
                        openChangeSignal: linkChangeSignal,
                        openNoteSignal: linkNoteSignal,
                        openEventsSignal: linkEventsSignal,
                        openHistorySignal: linkHistorySignal,
                        // ADR-089 step 3: what an email's extraction or an accepted finding added to the case.
                        onDelta: (delta) =>
                          workingSetRef.current.store.getState().applyDelta(delta as WorkingSetDelta),
                        onChanged: (result) => {
                          // The old link leaves the view and the new one arrives in one step; the Inspector
                          // is then pointed at the new link, whose id is not the old one's.
                          workingSetRef.current.store.getState().applyDelta(result.delta);
                          glassCanvasRef.current?.selectLink(result.edge.id);
                        },
                      }}
                      assessment={{
                        apiBaseUrl: API_BASE_URL,
                        bearerToken: bearerToken,
                        investigationId,
                        workingSetGraph: workingSetRef.current.graph,
                        onHighlightNodes: (nodeIds) =>
                          glassCanvasRef.current?.highlightNodes(nodeIds),
                        onJudgementsChange: (judgements) =>
                          setJudgementCounts(judgementCountsByNode(judgements)),
                      }}
                    />
                    </>
                  ),
                },
                ...(view === "graph"
                  ? [
                      {
                        id: "metrics" as const,
                        name: "Metrics",
                        content: (
                          <MetricsPanel
                            apiBaseUrl={API_BASE_URL}
                            bearerToken={bearerToken}
                            investigationId={investigationId}
                            graph={workingSetRef.current.graph}
                            onFocusNode={(nodeId) =>
                              glassCanvasRef.current?.focusOnNode(nodeId)
                            }
                            onCommunitiesChange={setCommunities}
                            onFilterChange={setMetricFilter}
                          />
                        ),
                      },
                    ]
                  : []),
                ...(view === "graph" && ontologySchema
                  ? [
                      {
                        id: "query-builder" as const,
                        name: "Query builder",
                        content: (
                          <QueryBuilderPanel
                            apiBaseUrl={API_BASE_URL}
                            bearerToken={bearerToken}
                            investigationId={investigationId}
                            schema={ontologySchema}
                          />
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          </SidePanelFrame>
        )}
      </div>
      {view !== "ingest" && view !== "dossier" && view !== "watches" && (
        // ADR-097 step 1: folded to its header by default, so the canvas has the room; opened and
        // sized as before (ADR-086).
        <BottomPanelFrame title="Timeline" height={252} initiallyOpen={false} openSignal={timelineOpenSignal}>
          <div style={{ height: "100%" }}>
            <Timeline
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationScope={investigationId}
              crossFilterStore={crossFilterStore}
              getNodeIds={() => workingSetRef.current.graph.nodes()}
              getEdgeIds={() => workingSetRef.current.graph.edges()}
              crossCaseInvestigationScope={crossCaseScope || undefined}
              onCrossCaseScopeChange={setCrossCaseScope}
              onPlaybackFractionChange={setPlaybackFraction}
            />
          </div>
        </BottomPanelFrame>
      )}
      </div>
      </div>
      {view !== "ingest" && view !== "dossier" && view !== "watches" && (
        <StatusBar
          nodeCount={counts.nodes}
          edgeCount={counts.edges}
          dimmedCount={dimmedNodeIds.size}
          filteredCount={counts.filteredCount}
          groupedCount={groupedCount}
        />
      )}
      <ProposedTypes
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        open={proposedTypesOpen}
        onClose={() => setProposedTypesOpen(false)}
        onDecided={() => setLinkTypesRead((n) => n + 1)}
      />
      <Drawer open={exploreOpen} onClose={() => setExploreOpen(false)} title="Explore">
        {investigationId && (
          <ExplorePanel
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            edgeTypes={edgeTypes}
            onPick={(node) => {
              pickToStart(node);
              setExploreOpen(false);
            }}
            onPickLink={(link) => {
              pickLinkToStart(link);
              setExploreOpen(false);
            }}
            onPickDay={(day) => {
              pickDay(day);
              setExploreOpen(false);
            }}
            onApplyDelta={applyStarterDelta}
          />
        )}
      </Drawer>
      <Drawer open={questionsOpen} onClose={() => setQuestionsOpen(false)} title="Questions">
        <QuestionsPanel
          apiBaseUrl={API_BASE_URL}
          bearerToken={bearerToken}
          investigationId={investigationId}
          onDelta={(delta) => workingSetRef.current.store.getState().applyDelta(delta as WorkingSetDelta)}
          onOpenDocument={(id) => {
            setReaderFallback(undefined);
            setReaderDocumentId(id);
          }}
        />
      </Drawer>
      {/* ADR-097 Amendment 1: the case's tabs, as a list in a panel from the rail. */}
      <Drawer open={casesOpen} onClose={() => setCasesOpen(false)} title="Cases">
        <div style={{ display: "grid", gap: "var(--sp-8)" }}>
          <CaseTabs
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            currentId={investigationId}
            isAdministrator={principal?.roles?.includes("osprey-admin") ?? false}
            layout="list"
            onOpen={(id) => {
              setCasesOpen(false);
              openCase(id);
            }}
          />
          <Button
            onClick={() => {
              setCasesOpen(false);
              setBrowsingCases(true);
            }}
          >
            Browse all cases
          </Button>
          {/* ADR-099: what the open case reads, changed by its Author. */}
          <CaseDatasets
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            onChanged={() => window.location.reload()}
          />
        </div>
      </Drawer>
      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        investigationId={investigationId}
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        onRestored={(snapshot) =>
          workingSetRef.current.store.getState().applyDelta(snapshot)
        }
      />
      <ExportPanel
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        investigationId={investigationId}
        graph={workingSetRef.current.graph}
        onExportChartImage={(mark) => {
          const handle = glassCanvasRef.current;
          if (!handle) {
            return Promise.reject(
              new Error("chart export: canvas is not mounted"),
            );
          }
          return handle.exportImage(mark);
        }}
      />
      {toast && (
        <div style={{ position: "fixed", bottom: 16, right: 16 }}>
          <Toast message={toast} />
        </div>
      )}
    </div>
  );
}
