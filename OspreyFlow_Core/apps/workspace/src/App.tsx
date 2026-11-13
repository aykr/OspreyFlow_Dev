import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "zustand/react";

import type {
  Edge,
  EdgeTypeDef,
  GeoBin,
  Node,
  OntologySchema,
  PublicMapConfig,
  Sighting,
  StrengthLegend,
} from "../../../packages/schemas/generated";
import { fetchSightings } from "./analytics/api";
import { followCrossFilterWithMapBins } from "./crossfilter/mapBins";
import {
  clearRedirectCallbackParams,
  completeSignInFromRedirect,
  displayPrincipal,
  fetchResolvedPrincipal,
  isSignInRedirectCallback,
  renewSilently,
  signIn,
  signInAgainInPlace,
  sessionFromUser,
  signOut,
  type ResolvedPrincipal,
  type SignedInSession,
} from "./auth/userManager";
import { clearHandoff, clearHandoffFromAddress, readHandoff } from "./auth/launcherHandoff";
import { SILENT_AT_LOAD_TIMEOUT_SECONDS, signInAtLoad } from "./auth/signInAtLoad";
import { installUnauthorisedWatch } from "./auth/unauthorised";
import { SessionPrompt } from "./auth/SessionPrompt";
import { createTokenRenewal, type RenewedUser, type TokenRenewal, watchActivity } from "./auth/tokenRenewal";
import { DISABLED_ACCOUNT_WORDS, isDisabledRefusal } from "./auth/disabledAccount";
import { SignInScreen } from "./auth/SignInScreen";
import { deploymentMarking, deploymentReportsUrl, deploymentWelcome } from "./auth/oidcConfig";
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
import { NeedsYou } from "./admin/needsYou/NeedsYou";
import { AnswersForSection } from "./home/AnswersForSection";
import { requestOpening, takeOpening } from "./admin/needsYou/openings";
import { AccountMenu } from "./auth/AccountMenu";
import { ClassificationStrip, screenMarking } from "./shell/ClassificationStrip";
import { LeftRail } from "./shell/LeftRail";
import { MORE_VIEWS, offeredViews, RAIL_LABELS, railMark, splitRail, splitViews, VIEW_LABELS, VIEW_SWITCH, viewToLandOn } from "./shell/railLayout";

const ALL_SWITCH_VIEWS = [...VIEW_SWITCH, ...MORE_VIEWS];
import { Drawer } from "./design/primitives/Drawer";
import { BuildAReportLink, TopBar } from "./shell/TopBar";
import { ContextBanner, crossLinkFor, useCaseContext } from "./shell/ContextBanner";
import { PlaceSwitcher } from "./shell/PlaceSwitcher";
import { useLastGlassView } from "./shell/placeMemory";
import { keepPlace, placeAtLoad, placeOnScreen, restorePlace } from "./auth/refreshPlace";
import { fetchHandlingScheme, type HandlingScheme } from "./ingest/api";
import { Button } from "./design/primitives/Button";
import { AccountUnread } from "./auth/AccountUnread";
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
import { seedElements } from "./connections/connectionsApi";
import { FindConnectionsPanel } from "./connections/FindConnectionsPanel";
import { ResolutionThresholdControl } from "./resolution/ThresholdControl";
import { placeableTypes, resolveNodeCoordinates } from "./map/geometries";
import { HotspotHistogram, locationEdgeTypeNames } from "./map/HotspotHistogram";
import { MapView } from "./map/MapView";
import { MatrixView } from "./matrix/MatrixView";
import { fetchCaseInfluencers } from "./strength/api";
import { searchPlaces } from "./map/places";
import { addGazetteer, caseGazetteers, removeGazetteer } from "./map/gazetteers";
import type { GazetteerControls } from "./map/MapControls";
import { defaultProvider, fetchMapConfig, switchableProviders } from "./map/providers";
import { instantAtFraction, itemsUpTo } from "./playback/math";
import {
  fetchOntologyRegistry,
  type OntologyRegistry,
} from "./ontology/schema";
import { fetchCaseLinkTypes, type CaseLinkTypes } from "./linktypes/linkTypesApi";
import { GlobalSearch } from "./search/GlobalSearch";
import { SearchResults } from "./search/SearchResults";
import { drawSearchResult } from "./search/drawSearchResult";
import { BoundaryFilterTool } from "./map/BoundaryFilterTool";
import { IngestStudio } from "./ingest/IngestStudio";
import { CasePicker } from "./investigation/CasePicker";
import { CaseSwitcher } from "./investigation/CaseSwitcher";
import { CaseList } from "./investigation/CaseList";
import { CaseAccessPanel } from "./investigation/CaseAccessPanel";
import { CaseSettings } from "./investigation/CaseSettings";
import { CaseBrief } from "./investigation/CaseBrief";
import type { AttachmentKind } from "./investigation/briefApi";
import { placeOf, revealPanel } from "./investigation/openAttachment";
import { caseIsOpenable, listCases, openCase, openCaseView } from "./investigation/cases";
import { caseForDataset } from "./ingest/studio/datasets";
import { buildLens, type Lens, lensWindow } from "./views/lens";
import { takeCaseView, withoutCaseView } from "./views/lensHandoff";
import { ViewLensBanner } from "./views/ViewLensBanner";
import { ViewsMenu } from "./views/ViewsMenu";
import { ViewsPanel } from "./views/ViewsPanel";
import { type CaseView, type CaseViewOpened, openView, saveView } from "./views/viewsApi";
import { bringFactIntoView } from "./questions/graphFacts";
import { QuestionsPanel } from "./questions/QuestionsPanel";
import { exploreOverlayPlace } from "./explore/exploreOverlayPlace";
import { ExplorePanel } from "./explore/ExplorePanel";
import type { BusyDay, RankedLink } from "./explore/exploreApi";
import { SiteCalibrationWizard } from "./site/SiteCalibrationWizard";
import { StatusBar } from "./statusbar/StatusBar";
import { emergence, type FirstSeen } from "./crossfilter/emergence";
import type { WorkingSetDelta } from "./workingset/models";
import { NO_FILTER, filterDimming, type MetricFilter } from "./metrics/filters";
import { BottomPanelFrame, SidePanelFrame } from "./layout/PanelFrames";
import { DEFAULT_TIMELINE_HEIGHT } from "./layout/layoutSizes";
import { useOnReturn } from "./strength/useOnReturn";
import { TimelineStrip } from "./timeline/TimelineStrip";
import { lastChangeText } from "./history/lastChange";
import type { HistoryStepSummary } from "./workingset/models";
import { guideUrl, openGuide } from "./home/guides";
import { setWelcomeDismissed, useHelpKey, welcomeDismissed, WorkspaceWelcome } from "./welcome/WorkspaceWelcome";
import { SidePanelStack } from "./layout/SidePanelStack";
import { Timeline } from "./timeline/Timeline";
import { RulesPlace } from "./alerts/RulesPlace";
import { evidenceCase, openAlertInItsCase, openRulesOnCase, useAlertAtAddress } from "./alerts/address";
import { StrengthPanel } from "./strength/StrengthPanel";
import { alertPath, navigate, noteAddress, takeNotedAddress, useAddress } from "./shell/router";
import { BoardsPlace } from "./boards/BoardsPlace";
import { EmbeddedDashboards } from "./reports/EmbeddedDashboards";
import { ReportsPlace } from "./reports/ReportsPlace";
import { ALERT_MONITORING, AlertMonitoringBoard } from "./reports/AlertMonitoringBoard";
import { journeyWords, startJourney, takeJourney, weeksFor, type AlertJourney } from "./reports/journey";
import { useAlertBadges } from "./reports/alertBadges";
import {
  canDownloadFeed,
  canKeepWatches,
  canRaiseAlerts,
  landingView,
  railEntries,
  showsInspector,
  type RailEntry,
  type StartPlace,
  startPlaces,
} from "./rights/visibility";
import { startScreen } from "./shell/startScreen";
import { loadHome, openInQueue, summariseHome, type HomeSummary } from "./home/homeData";
import { OwnershipPlace } from "./ownership/OwnershipPlace";
import {
  connectDeltaClient,
  type DeltaClient,
  type SocketLike,
} from "./workingset/deltaClient";
import { createWorkingSet } from "./workingset/store";
import { applyRestoredSnapshot, ViewOverCapGate } from "./workingset/ViewOverCapGate";

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
// build, so this path is dead code (and the variable read below moot) in anything
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
  // Read from the store itself, not copied into this component's own state by a subscription that a
  // change of case tears down: the reset on a new case would then never reach the bar.
  const withheld = useStore(workingSetRef.current.store, (s) => s.withheld);
  // ADR-124 decision 2: the server says the reader's own view is past a cap, and sends nothing
  // more until they try again. `ViewOverCapGate` shows the dialog; this holds the live client it
  // asks to resync, and a restore's own snapshot asks the same (`applyRestoredSnapshot`).
  const deltaClientRef = useRef<DeltaClient | null>(null);
  const resyncFromNothing = useCallback(() => deltaClientRef.current?.requestResync(null), []);
  const glassCanvasRef = useRef<GlassCanvasHandle>(null);
  const [groupedCount, setGroupedCount] = useState(0);
  // How many judgements rest on each node, drawn as a small count beside it (ADR-070).
  const [judgementCounts, setJudgementCounts] = useState<ReadonlyMap<string, number>>(new Map());
  // ADR-116: the degree from From of each node of a route put on the canvas by Find connections.
  const [degreeMarks, setDegreeMarks] = useState<ReadonlyMap<string, number>>(new Map());

  // `06_DECISIONS.md` ADR-050 — sign-in. `bearerToken` is the one value every child component
  // already took as a prop before this stage; only its *source* changes, from the dev-only
  // constant to the real access token this state holds once the analyst has signed in.
  const isDevBypass = Boolean(DEV_MODE_BEARER_TOKEN);
  const [bearerToken, setBearerToken] = useState<string>(DEV_MODE_BEARER_TOKEN);
  // ADR-112: what this person may do, so the Glass leaves out what it would only be refused. `null`
  // until known; the Conduit checks every right itself either way.
  const [rights, setRights] = useState<ReadonlySet<string> | null>(null);
  // Start waits for the rights, so a tile does not appear late or a single place go unnoticed.
  const [rightsSettled, setRightsSettled] = useState(false);
  // ADR-148 Amendment 8: who signed in (names only, from the ID token), and what the Conduit resolved
  // them to (`GET /v1/me`). The principal the Glass shows and gates on exists only once the Conduit
  // has answered: while it is asked, or when it does not answer, there is none, so no role-gated
  // control is offered. No role or clearance is ever read from a token.
  const [session, setSession] = useState<SignedInSession | null>(null);
  const [resolved, setResolved] = useState<ResolvedPrincipal | null>(null);
  const principal = useMemo(() => (resolved ? displayPrincipal(session, resolved) : null), [session, resolved]);
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
  // ADR-146 decision 6: an alert's address, kept over the sign-in round trip, which returns to the
  // root (`shell/router.ts`).
  useState(() => noteAddress());
  const address = useAddress();
  // ADR-050 Amendment 3: the place this tab was on when it was refreshed, unless the address says
  // where to go first (`auth/refreshPlace.ts`). Read once, before anything is drawn.
  const [restored] = useState(() => {
    const place = placeAtLoad(
      { autoSignIn: handoff.autoSignIn, pathname: window.location.pathname, search: window.location.search },
      sessionStorage,
    );
    return place ? restorePlace(place, initialInvestigationId() !== null, sessionStorage) : null;
  });
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
      const carriedACallback = isSignInRedirectCallback();
      if (carriedACallback) {
        try {
          const user = await completeSignInFromRedirect();
          clearRedirectCallbackParams();
          if (cancelled) return;
          setBearerToken(user.access_token);
          setSession(sessionFromUser(user));
          scheduleRenewal(user.expires_at);
          restoreViewStateAfterReauth();
          const noted = takeNotedAddress();
          if (noted) navigate(noted, { replace: true });
          signedIn = true;
          clearHandoff(sessionStorage);
        } catch {
          clearRedirectCallbackParams();
          if (!cancelled)
            setSignInReason("Your sign-in could not be completed. Try again.");
        }
      }
      // ADR-050 Amendment 3: no token in memory (a refresh, a new tab, a hand-off): ask the identity
      // provider's own session silently first, and show the screen only when it says no. Once per
      // load, shared by React's development double-run (`auth/signInAtLoad.ts`); never after a
      // refusal (that returned above, with an `error` parameter), and never after a completed or
      // failed callback. A hand-off with no session starts the full-page sign-in, as before.
      if (!cancelled && !signedIn && !carriedACallback) {
        const outcome = await signInAtLoad({
          silent: () => renewSilently({ silentRequestTimeoutInSeconds: SILENT_AT_LOAD_TIMEOUT_SECONDS }),
          redirect: () => signIn(),
          framed: window.parent !== window,
          autoSignIn: handoff.autoSignIn,
        });
        if (cancelled || outcome.kind === "redirected") return;
        if (outcome.kind === "signed-in") {
          const user = outcome.user;
          setBearerToken(user.access_token);
          setSession(sessionFromUser(user));
          scheduleRenewal(user.expires_at);
          restoreViewStateAfterReauth();
          // As the redirect's return to the root did: the hand-off is spent, so a later refresh
          // returns to the place refreshed rather than to the hand-off's.
          takeNotedAddress();
          clearHandoff(sessionStorage);
          clearHandoffFromAddress();
        } else if (outcome.reason) {
          setSignInReason(outcome.reason);
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
  // ADR-148 Amendment 8: the principal as the Conduit resolved it, asked afresh for every token.
  // Asked again on *Try again* (`resolvedAttempt`); when it does not answer the person is told so, and
  // can try again or sign out (the orchestrator's review of P10 part 2, item 3).
  const [resolvedAttempt, setResolvedAttempt] = useState(0);
  const [resolvedFailed, setResolvedFailed] = useState(false);
  useEffect(() => {
    setResolved(null);
    setResolvedFailed(false);
    if (!bearerToken) return;
    let cancelled = false;
    void fetchResolvedPrincipal(API_BASE_URL, bearerToken).then((found) => {
      if (cancelled) return;
      setResolved(found);
      setResolvedFailed(found === null);
    });
    return () => {
      cancelled = true;
    };
  }, [bearerToken, resolvedAttempt]);
  useEffect(() => {
    if (!bearerToken) {
      setRights(null);
      setRightsSettled(false);
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE_URL}/v1/me/rights`, { headers: { Authorization: `Bearer ${bearerToken}` } })
      .then((r) => (r.ok ? (r.json() as Promise<{ rights: string[] }>) : null))
      .then((found) => !cancelled && found && setRights(new Set(found.rights)))
      .catch(() => undefined)
      .finally(() => !cancelled && setRightsSettled(true));
    return () => {
      cancelled = true;
    };
  }, [bearerToken]);
  const bearerTokenRef = useRef(bearerToken);
  bearerTokenRef.current = bearerToken;
  // A new token is a new sign-in: a refusal of *it* is worth reacting to again.
  useEffect(() => {
    if (bearerToken) unauthenticatedHandledRef.current = false;
  }, [bearerToken]);

  // `06_DECISIONS.md` ADR-050 Amendment 1 (build order step 18b, rehearsal defect D1): the token is
  // renewed silently in the background before it expires, and after a refused call, through one
  // renewal at a time (`auth/tokenRenewal.ts`). The screens keep the token given at sign-in
  // (`bearerToken`), so a renewal changes no state and no screen reloads; the fetch watch below sends
  // the renewed token in its place. When renewal fails the page stays as it is and asks, in place.
  const renewedRef = useRef<{ for: string; token: string } | null>(null);
  const currentToken = useCallback(
    () =>
      renewedRef.current && renewedRef.current.for === bearerTokenRef.current
        ? renewedRef.current.token
        : bearerTokenRef.current,
    [],
  );
  const [sessionPrompt, setSessionPrompt] = useState<"ended" | "unreachable" | null>(null);
  const sessionPromptRef = useRef<"ended" | "unreachable" | null>(null);
  const [sessionPromptBusy, setSessionPromptBusy] = useState(false);
  const [sessionPromptProblem, setSessionPromptProblem] = useState<string | null>(null);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const askToSignInAgain = useCallback((why: "ended" | "unreachable" | null) => {
    sessionPromptRef.current = why;
    setSessionPrompt(why);
    setSessionPromptProblem(null);
  }, []);
  const adoptRenewedUser = useCallback(
    (user: RenewedUser) => {
      const signedIn = sessionRef.current;
      if (signedIn && user.profile.sub && user.profile.sub !== signedIn.sub) {
        // Somebody else signed in, in the sign-in window: a new sign-in, not a renewal.
        renewedRef.current = null;
        setBearerToken(user.access_token);
        setSession(sessionFromUser(user as never));
      } else {
        renewedRef.current = { for: bearerTokenRef.current, token: user.access_token };
      }
      askToSignInAgain(null);
    },
    [askToSignInAgain],
  );
  const renewalRef = useRef<TokenRenewal | null>(null);
  const expiresAtRef = useRef<number | undefined>(undefined);
  function scheduleRenewal(expiresAt: number | undefined): void {
    expiresAtRef.current = expiresAt;
    renewalRef.current?.schedule(expiresAt);
  }
  useEffect(() => {
    if (isDevBypass) return;
    const renewal = createTokenRenewal({
      renew: renewSilently,
      onRenewed: (user) => {
        expiresAtRef.current = user.expires_at;
        adoptRenewedUser(user);
      },
      onEnded: (why) => askToSignInAgain(why),
    });
    renewalRef.current = renewal;
    renewal.schedule(expiresAtRef.current);
    // ADR-050 Amendment 2: a renewal waits for the person to have done something since the last.
    const stopWatching = watchActivity(window, () => renewal.noteActivity());
    return () => {
      stopWatching();
      renewal.dispose();
      renewalRef.current = null;
    };
  }, [isDevBypass, adoptRenewedUser, askToSignInAgain]);

  /** A 401 on the very first authenticated call after sign-in means the token itself was refused
   * (wrong audience, a claim the realm never mapped) — retrying it against the same identity-
   * provider session would only fetch the identical bad token again. A 401 on any later call means
   * the token merely expired during use, and is renewed silently (ADR-050 Amendment 1): resolves
   * `true` when a renewed token is in place, so the refused call can be made once more. The two need
   * different reactions, and a bare 401 cannot tell them apart on its own — only "has this session
   * ever produced a usable token" can. */
  const renewAfterRefusal = useCallback(async (refusal?: Response): Promise<boolean> => {
    if (isDevBypass) return false;
    // ADR-148 Amendment 8: disabled in this deployment, said only when the Conduit says so; no
    // renewal is tried, since Entra would sign them in again to the same refusal.
    if (refusal && (await isDisabledRefusal(refusal))) {
      unauthenticatedHandledRef.current = true;
      setBearerToken("");
      setSession(null);
      setSignInReason(DISABLED_ACCOUNT_WORDS);
      return false;
    }
    if (!hasResolvedAPrincipalOnceRef.current) {
      // Once per sign-in: several calls refused together say it once.
      if (unauthenticatedHandledRef.current) return false;
      unauthenticatedHandledRef.current = true;
      setBearerToken("");
      setSession(null);
      setSignInReason(
        "Your sign-in could not be used to reach the workspace. Check with your " +
          "administrator that this deployment's identity provider is configured correctly.",
      );
      return false;
    }
    // The person has been asked to sign in again: nothing more is tried until they answer.
    if (sessionPromptRef.current !== null) return false;
    const renewal = renewalRef.current;
    if (!renewal) return false;
    // A call refused while nobody has done anything (a screen's own poll) is not renewed, so an
    // unattended window still reaches the identity provider's idle limit (ADR-050 Amendment 2); the
    // person's next action renews, and a call they make then is renewed as before.
    return (await renewal.renewIfActive()).kind === "renewed";
  }, [isDevBypass]);
  const handleUnauthenticatedResponse = useCallback((): void => {
    void renewAfterRefusal();
  }, [renewAfterRefusal]);

  const signInAgain = useCallback(async (): Promise<void> => {
    setSessionPromptBusy(true);
    setSessionPromptProblem(null);
    try {
      const user = await signInAgainInPlace();
      adoptRenewedUser(user);
      scheduleRenewal(user.expires_at);
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      setSessionPromptProblem(
        /closed/i.test(message)
          ? "The sign-in window was closed before you had signed in. Sign in again to carry on."
          : "The sign-in window could not be opened. Allow pop-up windows for this address, then sign in again.",
      );
    } finally {
      setSessionPromptBusy(false);
    }
  }, [adoptRenewedUser]);
  const tryRenewingAgain = useCallback((): void => {
    askToSignInAgain(null);
    void renewalRef.current?.renewNow();
  }, [askToSignInAgain]);

  // A 401 from the Conduit on *any* call carrying the signed-in token means the sign-in has gone
  // stale, whichever screen made the call (3 October 2026: the Ingest Studio and the case menu
  // showed raw 401s after the identity provider was restarted, because only the Glass's own calls
  // were wired to the handler above). Watching `fetch` once covers every screen, present and future.
  useEffect(() => {
    if (isDevBypass) return;
    return installUnauthorisedWatch({
      apiBaseUrl: API_BASE_URL,
      getToken: () => bearerTokenRef.current,
      currentToken,
      onUnauthorised: renewAfterRefusal,
    });
  }, [isDevBypass, currentToken, renewAfterRefusal]);

  // The case picker shown over an open case ("All cases" in the header). It replaces the workspace
  // in the render, it does not unmount `App`, so the sign-in and the per-case state survive.
  const [browsingCases, setBrowsingCases] = useState(false);
  // ADR-114 Amendment 5 point 9: Start, or the place chosen on it, while outside a case's workspace.
  // `null` with a case open is the workspace itself; a hand-off naming the Studio or Admin is a choice.
  // ADR-145 decision 1: Admin is a place of its own, outside any case, so a hand-off naming it opens
  // it even with a case open; a hand-off is only a wish, checked against the rights below.
  const [startChoice, setStartChoice] = useState<StartPlace | "start" | null>(() =>
    restored
      ? restored.startChoice
      : handoff.view === "admin" ? "admin" : initialInvestigationId() ? null : handoff.view === "ingest" ? "ingest" : null,
  );
  const [investigationId, setInvestigationId] = useState<string | null>(
    initialInvestigationId(),
  );
  // ADR-115 E3: Home's figures, read whenever Home is on screen — each from a route the person's
  // rights open, counted as them.
  const [homeSummary, setHomeSummary] = useState<HomeSummary | null>(null);
  const onHome = rightsSettled && !!bearerToken && (startChoice === "start" || (!investigationId && startChoice === null));
  useEffect(() => {
    if (!onHome || !bearerToken) return;
    let cancelled = false;
    setHomeSummary(null);
    void loadHome({
      apiBaseUrl: API_BASE_URL,
      bearerToken,
      rights: rights ?? new Set(),
      me: principal?.sub ?? "",
      lastCaseId: investigationIdFromSession(),
    }).then((read) => {
      if (!cancelled) setHomeSummary(summariseHome(read));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onHome, bearerToken, rights]);
  // Phase 7 Stage 3: the metrics panel's own "Show community hulls" toggle feeds this, `App.tsx`
  // (not `MetricsPanel` itself) turns it into hull geometry — `MetricsPanel` has no dependency on
  // Sigma/the canvas at all, the same separation `onSelectionChange`/`onViewMessages` already draw
  // between "what happened" and "what the canvas does about it."
  const [communities, setCommunities] = useState<Record<string, string> | null>(
    null,
  );
  const [ontology, setOntology] = useState<OntologyRegistry | null>(null);
  const [ontologyEdgeTypes, setEdgeTypes] = useState<EdgeTypeDef[]>([]);
  // A hotspot is a place: the panel counts events on links ending at a Location, and shows only
  // when the ontology has such links (9 October 2026).
  // ADR-105: the entity types a picture of its own may depict.
  const pictureTypes = useMemo(
    () => new Set(ontologyEdgeTypes.find((t) => t.name === "DEPICTS")?.to ?? []),
    [ontologyEdgeTypes],
  );
  // P6: the case's gazetteers beside the map's place search, bound once per case, token and
  // rights, so the panel reads them once rather than on every render. Changes are offered only to
  // a person holding `run_pipelines`; the Conduit refuses anyone else all the same.
  // The calls are bound to the case and token alone, so the rights arriving re-read nothing.
  const gazetteerCalls = useMemo(
    () =>
      investigationId
        ? {
            load: () => caseGazetteers(API_BASE_URL, bearerToken, investigationId),
            add: (datasetId: string, gazetteerId: string) =>
              addGazetteer(API_BASE_URL, bearerToken, datasetId, gazetteerId),
            remove: (datasetId: string, gazetteerId: string) =>
              removeGazetteer(API_BASE_URL, bearerToken, datasetId, gazetteerId),
          }
        : undefined,
    [investigationId, bearerToken],
  );
  const mayChangeGazetteers = rights?.has("run_pipelines") ?? false;
  const gazetteerControls = useMemo<GazetteerControls | undefined>(
    () => gazetteerCalls && { ...gazetteerCalls, mayChange: mayChangeGazetteers },
    [gazetteerCalls, mayChangeGazetteers],
  );
  const hotspotEdgeTypes = useMemo(
    () => locationEdgeTypeNames(ontologyEdgeTypes),
    [ontologyEdgeTypes],
  );
  // ADR-090: the types a link in this case may take, read from the case: the ontology's, and those
  // analysts proposed in it, its parents or on a link in view, so a proposed type is named and drawn
  // in its own colour, dotted. `null` until read, or when the read fails: the ontology's alone.
  const [caseLinkTypes, setCaseLinkTypes] = useState<CaseLinkTypes | null>(null);
  const [linkTypesRead, setLinkTypesRead] = useState(0);
  // ADR-139 decision 7: the case's connection-strength legend (the influencers in force), read again
  // whenever the influencer editor saves (`strengthRead`).
  const [strengthLegend, setStrengthLegend] = useState<StrengthLegend | null>(null);
  const [strengthRead, setStrengthRead] = useState(0);
  // D9 (build order step 18c): a composition or influencer changed in another window is shown when
  // the analyst comes back to this one, not only once the legend is reopened.
  useOnReturn(() => setStrengthRead((n) => n + 1));
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
  // The search results page (ADR-145 Amendment 15 Part A): the words searched and the view's name the person left.
  // While it shows, it fills the main area over that view, which stays as it was beneath it, and no view is current.
  const [searching, setSearching] = useState<{ query: string; left: string } | null>(null);
  // Back from the results: focus returns to the search box once the view beneath is reachable again.
  const focusSearchBox = useRef(false);
  useEffect(() => {
    if (searching !== null || !focusSearchBox.current) return;
    focusSearchBox.current = false;
    document.querySelector<HTMLElement>('.top-bar [role="combobox"]')?.focus();
  }, [searching]);
  // The Ask line's words, carried into Ask & Chat's question box, not sent.
  const [questionDraft, setQuestionDraft] = useState<{ text: string; at: number } | null>(null);
  // Another case is another search: its results are not this one's.
  useEffect(() => setSearching(null), [investigationId]);
  // The types the map places (`placeableTypes`): read by the working-set subscription, which is
  // registered once, so a ref rather than the schema state it is worked out from.
  const placeableRef = useRef<ReadonlySet<string>>(placeableTypes(null));
  placeableRef.current = placeableTypes(ontologySchema);
  /** ADR-100: an Explore item does what choosing a search result does: draws it and selects it. */
  const pickToStart = (node: Node) => {
    void drawSearchResult((nodes) => seedToCanvas(nodes, []), node, glassCanvasRef.current);
    setSelectedNode(node);
  };
  /** What Explore adds goes to the case's working set through `/seed`, as a found route does, and is
   * drawn from the change the Conduit answers — so the working set holds it and the canvas's
   * counters and legend see it. A local add did neither (the Glass review, 18 October 2026). */
  const seedToCanvas = async (nodes: readonly Node[], edges: readonly Edge[]): Promise<boolean> => {
    if (!investigationId) return false;
    const { graph, store } = workingSetRef.current;
    try {
      const delta = await seedElements(
        { apiBaseUrl: API_BASE_URL, bearerToken, investigationId },
        nodes,
        edges,
        { hasNode: (id) => graph.hasNode(id), hasEdge: (id) => graph.hasEdge(id) },
      );
      if (delta) store.getState().applyDelta(delta);
      return true;
    } catch (error) {
      setToast(error instanceof Error ? error.message : String(error));
      return false;
    }
  };
  /** ADR-100 decision 5: a busiest link puts the pair and their link on the canvas. */
  const pickLinkToStart = (link: RankedLink) => {
    void seedToCanvas([link.source, link.target], [link.edge]);
    setSelectedNode(link.source);
  };
  /** ADR-100 Amendment 9: a node with its chosen busiest links, each with both ends, drawn; with no
   * links, *Just this entity* — the node alone. */
  const addWithBusiest = (node: Node, links: RankedLink[]) => {
    void seedToCanvas(
      [node, ...links.flatMap((l) => [l.source, l.target])],
      links.map((l) => l.edge),
    );
    setSelectedNode(node);
  };
  /** ADR-100 Amendment 9: "with all n links…" — the node, then the canvas's own one-link expand,
   * whose large-expansion question already guards the all case. Not a search's three-link draw. */
  const expandAllOf = async (node: Node) => {
    setSelectedNode(node);
    if (await seedToCanvas([node], [])) glassCanvasRef.current?.expandFrom(node.id, 1);
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
  // ADR-105 Amendment 1: the node menu's *Set picture…* opens the Inspector's Picture part.
  const [pictureOpenSignal, setPictureOpenSignal] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  // ADR-115 E6: the workspace's welcome panel — open until this person closes it once — and `?`.
  // ADR-145 Amendment 12: "auto", opened at sign-in, is shown on the graph alone, as before; "asked",
  // by Help or `?`, is shown over whichever view is on screen.
  const [welcome, setWelcome] = useState<"closed" | "auto" | "asked">("closed");
  const welcomeDecided = useRef(false);
  useEffect(() => {
    if (welcomeDecided.current || !principal?.sub) return;
    welcomeDecided.current = true;
    setWelcome(welcomeDismissed(principal.sub) ? "closed" : "auto");
  }, [principal?.sub]);
  // Set as the Glass is drawn (below): whether the panel is shown, how it closes, and whether `?` is
  // the Glass's here (elsewhere, the Studio, Rules and Monitoring, Home, it does nothing).
  const shownWelcomeRef = useRef(false);
  const closeWelcomeRef = useRef<() => void>(() => undefined);
  const helpHereRef = useRef(false);
  const toggleWelcome = useCallback(() => {
    if (!helpHereRef.current) return;
    if (shownWelcomeRef.current) closeWelcomeRef.current();
    else setWelcome("asked");
  }, []);
  useHelpKey(toggleWelcome);
  // ADR-097 Amendment 1: the cases, and the views of each (ADR-144 decision 5), reached from the case line.
  // The Cases panel, and where it opened (Amendment 15): at its views list from *Views in this case*, or whole from
  // the case menu's *All cases*.
  const [casesOpen, setCasesOpen] = useState<false | "views" | "all">(false);
  // ADR-144 and the owner's ruling of 8 November 2026 (Amendment 2): an opened view, shown on the
  // canvas as a read-only lens over the case, and `viewsRead` bumped to read the views again.
  const [lens, setLens] = useState<Lens | null>(null);
  // ADR-146 decision 6: the alert a view was opened from (*Open the evidence*), for the lens's way
  // back to it, still open; `null` for a view opened any other way.
  const [lensFromAlert, setLensFromAlert] = useState<{ alertId: string; title: string } | null>(null);
  const [viewsRead, setViewsRead] = useState(0);
  const [viewProblem, setViewProblem] = useState<string | null>(null);
  // ADR-144 decision 4: the view *Ask the model about these* saved, whose conversation is open.
  const [questionsView, setQuestionsView] = useState<{ id: string; name: string } | null>(null);
  // ADR-128 decision 3: opening a saved trend from the case brief starts the Reports view on Trends;
  // the count re-mounts the place so a second open starts there again.
  const [reportsStart, setReportsStart] = useState<{ tab?: "trends"; opened: number }>({ opened: 0 });
  // ADR-098 decision 4: the case's questions to the model, open at once when the case was opened on them.
  const [questionsOpen, setQuestionsOpen] = useState(handoff.view === "questions");
  // ADR-100: where to start in a case's data, from the rail (and over an empty canvas).
  const [exploreOpen, setExploreOpen] = useState(false);
  // ADR-097 step 1 (review item 16): the deployment's classifications, lowest first, for the strip.
  const [classificationOrder, setClassificationOrder] = useState<readonly string[]>([]);
  // ADR-102: the scheme, so a link's handling can be changed on purpose.
  const [handlingScheme, setHandlingScheme] = useState<HandlingScheme | undefined>(undefined);
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
    return screenMarking(found, classificationOrder, deploymentMarking());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counts, classificationOrder]);

  const [view, setView] = useState<
    "graph" | "map" | "matrix" | "reports" | "dashboards" | "ingest" | "dossier" | "alerts" | "ownership" | "strength" | "boards"
  >(
    (restored?.view as "graph" | "map" | "matrix" | "reports" | "dashboards" | "ingest" | "alerts" | "ownership" | "strength" | null | undefined) ??
      (handoff.view === "ingest" ? "ingest" : address.kind !== "none" ? "alerts" : "graph"),
  );
  // ADR-143 decision 5 (L3.3): a board opened at once, after a drawing with no case made its case.
  const [boardToOpen, setBoardToOpen] = useState<string | null>(null);
  // ADR-115 E6: the canvas toolbar's "Last change", read again as the working set changes.
  const [lastChange, setLastChange] = useState<string | null>(null);
  useEffect(() => {
    if (!investigationId || !bearerToken) return;
    let cancelled = false;
    void fetch(`${API_BASE_URL}/v1/investigations/${encodeURIComponent(investigationId)}/history`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      .then((r) => (r.ok ? (r.json() as Promise<unknown>) : []))
      .then((body) => !cancelled && setLastChange(lastChangeText(Array.isArray(body) ? (body as HistoryStepSummary[]) : [], new Date())))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [investigationId, bearerToken, counts.nodes, counts.edges]);
  // ADR-115 E6: the open-alert count, the case's queue counted as the reader (rule 3), drawn on the
  // switcher's Rules and Monitoring since ADR-146 decision 2 (it left the Glass's banner).
  const [alertCount, setAlertCount] = useState<number | undefined>(undefined);
  const opensRules = startPlaces(rights).includes("rules");
  // ADR-145 Amendment 4 decision 10: the Reports Viewer's journey from an alert on Home, noted over the
  // case switch's reload (`reports/journey.ts`) and taken once the case is open: its Figures, or the
  // Alert monitoring board filtered to the alert. A reader offered Rules and Monitoring opens alerts
  // at their address instead, and the Figures' and the board's Alerts panels open them there too.
  const [alertJourney, setAlertJourney] = useState<AlertJourney | null>(null);
  useEffect(() => {
    if (!investigationId || !bearerToken) return;
    const taken = takeJourney(investigationId);
    if (!taken) return;
    setAlertJourney(taken);
    setView(taken.to === "figures" ? "reports" : "dashboards");
  }, [investigationId, bearerToken]);
  // The journey's banner and outline belong to the screen it opened: leaving that screen ends it.
  useEffect(() => {
    if (alertJourney && view !== (alertJourney.to === "figures" ? "reports" : "dashboards")) setAlertJourney(null);
  }, [view, alertJourney]);
  const journeyBack = alertJourney
    ? { words: journeyWords(alertJourney), onBack: () => { setAlertJourney(null); setStartChoice("start"); } }
    : null;
  const openAlertFromPanel = opensRules ? (alertId: string) => navigate(alertPath(alertId)) : undefined;
  // ADR-146 decision 9: the canvas's alert badge, from the reader's own queue of the open case.
  const alertBadges = useAlertBadges(
    investigationId && bearerToken && rights?.has("read_alert_queue") ? { apiBaseUrl: API_BASE_URL, bearerToken, investigationId } : null,
  );
  useEffect(() => {
    if (!investigationId || !bearerToken || !opensRules) {
      setAlertCount(undefined);
      return;
    }
    let cancelled = false;
    void fetch(`${API_BASE_URL}/v1/investigations/${encodeURIComponent(investigationId)}/alert-queue`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      .then((r) => (r.ok ? (r.json() as Promise<{ alert: { status: string } }[]>) : null))
      .then((queue) => {
        if (cancelled) return;
        setAlertCount(Array.isArray(queue) ? openInQueue(queue) : undefined);
      })
      .catch(() => !cancelled && setAlertCount(undefined));
    return () => {
      cancelled = true;
    };
    // The count is read again when the analyst comes back from Rules and Monitoring.
  }, [investigationId, bearerToken, opensRules, view]);
  // ADR-146 decision 6: an alert's address opens Rules and Monitoring on it, in the case the
  // Conduit says it is worked in; another case's is opened on the alert (a reload, as every case
  // switch is). Leaving the address (Back, or Back to the queue) leaves the alert, not the place.
  const addressedAlert = address.kind === "alert" ? address.alertId : null;
  const addressed = useAlertAtAddress(API_BASE_URL, bearerToken, opensRules ? addressedAlert : null);
  const rulesAddressed = address.kind === "rules" || addressedAlert !== null;
  useEffect(() => {
    if (rulesAddressed && opensRules) setView("alerts");
  }, [rulesAddressed, opensRules]);
  // ADR-145 N6 and ADR-146 decision 2: the place is drawn only for whom it is offered. Someone else
  // following an address (an email's link) lands on the Glass, the address left; the Conduit would
  // refuse the place's routes anyway (its gate), but for the two lists read outside it.
  useEffect(() => {
    if (!rightsSettled || opensRules || view !== "alerts") return;
    setView(landingView(rights));
    if (address.kind !== "none") navigate("/", { replace: true });
  }, [rightsSettled, opensRules, view, rights, address.kind]);
  useEffect(() => {
    if (addressed?.status === "found" && addressedAlert && addressed.caseId !== investigationId) {
      openAlertInItsCase(addressedAlert, addressed.caseId);
    }
  }, [addressed, addressedAlert, investigationId]);
  // Which place is open, and (so the switch can go back to it) the Glass view last open.
  const app = view === "ingest" ? "ingest" : view === "alerts" ? "rules" : "glass";
  // ADR-128 decision 3: an attachment of the case brief opens where the thing lives (`openAttachment.ts`).
  const openBriefAttachment = (kind: AttachmentKind, id: string) => {
    const place = placeOf(kind, id);
    setCasesOpen(false);
    if (place.place === "case") {
      openCase(id);
    } else if (place.place === "reports") {
      setReportsStart((now) => ({ tab: place.tab, opened: now.opened + 1 }));
      setView("reports");
    } else {
      setView("graph");
      // The side panels are on the page once the graph view is drawn: reveal one on the next tick.
      window.setTimeout(() => revealPanel(place.panel), 0);
    }
  };
  // ADR-145 decision 2: the Glass's view to come back to from the Studio (`shell/placeMemory.ts`).
  // The views kept are `KEPT_GLASS_VIEWS` (Messages is not), shared with the keyboard harness.
  const lastGlassView = useLastGlassView(view, "ingest", "graph");
  // ADR-050 Amendment 3: the place on screen, kept for a refresh of this tab. Only once signed in and
  // the rights are known, so the screens shown before (and the landing checks' corrections) are not
  // taken for the person's place; the case list over a case is not a place of its own.
  useEffect(() => {
    if (!bearerToken || !rightsSettled || browsingCases) return;
    keepPlace(placeOnScreen(startChoice, view, investigationId !== null, startPlaces(rights)), sessionStorage);
  }, [bearerToken, rightsSettled, browsingCases, startChoice, view, investigationId, rights]);
  // ADR-109 phase B: an alert put on the canvas is highlighted once the canvas has drawn it.
  const pendingHighlight = useRef<string[] | null>(null);
  useEffect(() => {
    if (view !== "graph" || !pendingHighlight.current) return;
    const ids = pendingHighlight.current;
    pendingHighlight.current = null;
    const frame = requestAnimationFrame(() => glassCanvasRef.current?.highlightNodes(ids));
    return () => cancelAnimationFrame(frame);
  }, [view]);
  // The Matrix view's Expand and Show (02_GLASS_FRONTEND.md §6, GDS remediation plan A1): done by the
  // canvas itself once the Graph is drawn — Expand through its own preview and the working set's cap
  // (rule 2), never a second expansion path.
  const pendingCanvasAction = useRef<{ kind: "expand" | "show"; nodeId: string } | null>(null);
  useEffect(() => {
    if (view !== "graph" || !pendingCanvasAction.current) return;
    const { kind, nodeId } = pendingCanvasAction.current;
    pendingCanvasAction.current = null;
    const frame = requestAnimationFrame(() => {
      if (kind === "expand") glassCanvasRef.current?.expandNode(nodeId);
      else glassCanvasRef.current?.focusOnNode(nodeId);
    });
    return () => cancelAnimationFrame(frame);
  }, [view]);
  // ADR-145 N6: the Studio, reached by a hand-off (`?view=ingest`) with a case open, is drawn only if
  // the person's rights open it; otherwise the Glass's own landing view. (A place chosen outside a
  // case is checked where it is drawn, in `shell/startScreen.tsx`.) Hiding is not the control — the
  // routes refuse anyway; this keeps the screen from offering what would be refused.
  useEffect(() => {
    if (rightsSettled && view === "ingest" && !startPlaces(rights).includes("ingest")) setView(landingView(rights));
  }, [rights, rightsSettled, view]);
  // ADR-145 decision 2: the banner's case and the datasets it reads, as this person may see them.
  const caseContext = useCaseContext(API_BASE_URL, bearerToken, investigationId);
  // ADR-112: someone who may not investigate (a Reports Viewer) lands where they may look. ADR-145 Amendment 15: any
  // view of the switch this person is not offered gives way (one chosen before the rights arrived, or a refresh's),
  // so exactly one view stays current, the Administrator's Connection strength among them.
  useEffect(() => {
    const offered: readonly string[] = offeredViews(rights);
    if ((ALL_SWITCH_VIEWS as readonly string[]).includes(view) && !offered.includes(view)) {
      setView(viewToLandOn(rights) as typeof view);
    }
  }, [rights, view]);
  const [dossierNodeId, setDossierNodeId] = useState<string | null>(null);
  // ADR-092: the Document open in the full-screen reader, if any.
  const [readerDocumentId, setReaderDocumentId] = useState<string | null>(null);
  // ADR-092 Amendment 3: an email opened from the Inspector, shown until its Document exists.
  const [readerFallback, setReaderFallback] = useState<DocumentReaderView | undefined>(undefined);
  // ADR-093: every node selected on the canvas, for the Inspector's list.
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  // The selection made where no canvas is drawn (the Matrix view): the same state the canvas reports
  // to, so the Inspector shows it and the canvas opens with it. Selecting nodes clears the link and
  // the other way round, as on the canvas.
  const selectNodesOffCanvas = (nodeIds: string[]) => {
    const graph = workingSetRef.current.graph;
    const present = nodeIds.filter((id) => graph.hasNode(id));
    setSelectedNodeIds(present);
    setSelectedLink(null);
    setSelectedNode(present[0] ? graph.getNodeAttribute(present[0], "data") : null);
  };
  const selectLinkOffCanvas = (edgeId: string | null) => {
    const graph = workingSetRef.current.graph;
    setSelectedNodeIds([]);
    setSelectedNode(null);
    setSelectedLink(edgeId && graph.hasEdge(edgeId) ? graph.getEdgeAttribute(edgeId, "data") : null);
  };
  const showOnGraph = (nodeId: string) => {
    selectNodesOffCanvas([nodeId]);
    pendingCanvasAction.current = { kind: "show", nodeId };
    setView("graph");
  };
  const expandOnGraph = (nodeId: string) => {
    selectNodesOffCanvas([nodeId]);
    pendingCanvasAction.current = { kind: "expand", nodeId };
    setView("graph");
  };
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

  // ADR-144 (the owner's ruling of 8 November 2026, Amendment 2): an opened view takes the canvas's
  // place as a read-only lens. Its window goes to the timeline, as the case's would; the Conduit has
  // already collapsed its items at its threshold. "Back to the case" puts the case's canvas back.
  // The case's own timeline window while a view is open, given back on *Back to the case*.
  const caseWindowRef = useRef<{ validFrom: string; validTo: string | null } | null | undefined>(undefined);
  // The latest view asked for: an earlier answer arriving after it is dropped.
  const lensAskedRef = useRef(0);

  function showLens(opened: CaseViewOpened, fromAlert: { alertId: string; title: string } | null = null): void {
    // Whatever opened this view, an earlier `openLens` still in flight no longer replaces it.
    lensAskedRef.current += 1;
    setViewProblem(null);
    const timeline = crossFilterRef.current?.store.getState();
    if (caseWindowRef.current === undefined) caseWindowRef.current = timeline?.window ?? null;
    setLens(buildLens(opened));
    // A view opened from an alert (*Open the evidence*) keeps the way back to it; any other has none.
    setLensFromAlert(fromAlert);
    setSelectedNodeIds([]);
    setSelectedNode(null);
    // The view's window, or none: a view keeps no window of the case's.
    timeline?.setWindow(lensWindow(opened));
    setView("graph");
  }

  /** Opens a view as the lens; resolves to the words said when it could not be opened (also shown
   * over the canvas), or `null` when it was, or when a later request replaced this one. */
  async function openLens(viewId: string, fromAlert: { alertId: string; title: string } | null = null): Promise<string | null> {
    if (!investigationId) return null;
    const asked = ++lensAskedRef.current;
    const result = await openView(API_BASE_URL, bearerToken, investigationId, viewId);
    if (asked !== lensAskedRef.current) return null;
    if (result.ok) {
      showLens(result.opened, fromAlert);
      return null;
    }
    const problem =
      result.kind === "not_found"
        ? "That view could not be opened. It may have been deleted, or not shared with you."
        : result.kind === "limit_exceeded"
          ? `This view holds more than the canvas can: ${result.wouldBe.would_be.toLocaleString("en-GB")} ${result.wouldBe.cap_kind === "nodes" ? "nodes" : "links"} against a limit of ${result.wouldBe.cap.toLocaleString("en-GB")}. Nothing was cut to fit.`
          : result.message;
    setViewProblem(problem);
    return problem;
  }

  function closeLens(): void {
    lensAskedRef.current += 1;
    setLens(null);
    setLensFromAlert(null);
    setViewProblem(null);
    setSelectedNodeIds([]);
    setSelectedNode(null);
    if (caseWindowRef.current !== undefined) {
      crossFilterRef.current?.store.getState().setWindow(caseWindowRef.current);
      caseWindowRef.current = undefined;
    }
    if (new URL(window.location.href).searchParams.has("case_view")) {
      window.history.replaceState(window.history.state, "", withoutCaseView(window.location.href));
    }
  }

  // A case opened on one of its views (from another case's row in the Cases drawer): opened once the
  // case and the sign-in are there.
  const caseViewTaken = useRef(false);
  useEffect(() => {
    if (caseViewTaken.current || !investigationId || !bearerToken) return;
    caseViewTaken.current = true;
    const viewId = takeCaseView(investigationId, window.location.search);
    // Taken once: the address no longer names it, so a reload opens the case, and a view that could
    // not be opened is not asked for again.
    if (new URL(window.location.href).searchParams.has("case_view")) {
      window.history.replaceState(window.history.state, "", withoutCaseView(window.location.href));
    }
    if (viewId) void openLens(viewId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per case load, by design
  }, [investigationId, bearerToken]);

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
    if (!bearerToken || !investigationId) {
      setStrengthLegend(null);
      return;
    }
    let current = true;
    fetchCaseInfluencers(API_BASE_URL, bearerToken, investigationId)
      .then((found) => {
        if (current) setStrengthLegend(found.legend);
      })
      .catch(() => {
        if (current) setStrengthLegend(null);
      });
    return () => {
      current = false;
    };
  }, [bearerToken, investigationId, strengthRead]);

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

  // A case this account cannot open is dropped, so the picker shows: signing in as a second account
  // reopened the first one's case from the tab, every panel was refused and one of them blanked the
  // Glass (9 October 2026). Asked once the account is known; a failing server keeps the case.
  useEffect(() => {
    if (!investigationId || !bearerToken || isDevBypass) return;
    let cancelled = false;
    void caseIsOpenable(API_BASE_URL, bearerToken, investigationId).then((openable) => {
      if (cancelled || openable) return;
      sessionStorage.removeItem(INVESTIGATION_ID_SESSION_KEY);
      setInvestigationId(null);
    });
    return () => {
      cancelled = true;
    };
  }, [investigationId, bearerToken, isDevBypass]);

  // A case's degree marks are its own: another case opens with none.
  useEffect(() => setDegreeMarks(new Map()), [investigationId]);

  // What the open case withholds from this reader is the case's own (ADR-124 decision 5): another
  // case opens knowing nothing of it until its snapshot says. Declared before the stream's effect so
  // it runs first on a change of case.
  useEffect(() => workingSetRef.current.store.getState().resetCase(), [investigationId]);

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
    const unsubscribe = workingSet.store.subscribe(() => {
      setCounts({
        nodes: workingSet.graph.order,
        edges: workingSet.graph.size,
      });
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
        placeableRef.current,
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
    // WebSocket authenticates on connect and on every reconnect": a new sign-in tears this effect
    // down and re-establishes the connection with a freshly minted ticket. A background renewal
    // (ADR-050 Amendment 1) does not change `bearerToken`, so the open socket, authenticated once at
    // connect by its single-use ticket, stays open; a new connection's ticket is asked for with the
    // renewed token (the fetch watch sends it).
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
          {
            onDelta: (delta) => workingSet.store.getState().applyDelta(delta),
            onViewOverCap: (wouldBe) => workingSet.store.getState().setViewOverCap(wouldBe),
          },
        );
        deltaClientRef.current = client;
      });
    return () => {
      cancelled = true;
      client?.close();
      deltaClientRef.current = null;
      unsubscribe();
    };
  }, [investigationId, bearerToken, handleUnauthenticatedResponse]);

  // Keyed by the store itself, not the case: the store is made only once there is a token, which a
  // sign-in through the identity provider delivers after this first ran (8 October 2026: a brush
  // dimmed nothing in the deployed Glass, while `npm run dev`'s token was there from the start).
  const crossFilterForDimming = crossFilterRef.current;
  useEffect(() => {
    if (!crossFilterForDimming) return;
    const unsubscribe = crossFilterForDimming.store.subscribe((state) => {
      setDimming({
        dimmedNodeIds: state.dimmedNodeIds,
        dimmedEdgeIds: state.dimmedEdgeIds,
        firstSeen: state.firstSeen,
        dimmedCount: state.dimmedCount,
      });
    });
    return () => unsubscribe();
  }, [crossFilterForDimming]);

  useEffect(() => {
    const crossFilter = crossFilterRef.current;
    if (!crossFilter || !investigationId) return;
    const scope = investigationId;
    // Unlike the timeline's own density strip (`timeline/Timeline.tsx`'s
    // own comment on why it always shows the full range), the map's heat
    // layer *does* restrict to the active brush window — `02_GLASS_
    // FRONTEND.md` §3.4's "the map restricts to it" is this bullet, named
    // literally.
    const unsubscribe = followCrossFilterWithMapBins(
      crossFilter.store,
      API_BASE_URL,
      bearerToken,
      scope,
      GEO_BIN_PRECISION,
      setGeoBins,
    );
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
    // The chosen weekly cells narrow the trail as they narrow the dimming (ADR-130 Amendment 1).
    // A newer read supersedes an older one, so a slow older answer arriving last is dropped.
    let latest = 0;
    function refresh(
      window: CrossFilterStoreState["window"],
      cells: CrossFilterStoreState["cells"],
    ) {
      latest += 1;
      const mine = latest;
      if (!window) {
        setSightings([]);
        return;
      }
      void fetchSightings(API_BASE_URL, bearerToken, {
        filter: buildEventFilter(scope, window, [entityId], cells),
      }).then((result) => {
        if (!cancelled && mine === latest) setSightings(result);
      });
    }
    const initial = crossFilter.store.getState();
    refresh(initial.window, initial.cells);
    const unsubscribe = crossFilter.store.subscribe((state) =>
      refresh(state.window, state.cells),
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
  // not an error page and not an empty workspace." Checked before the "not ready yet" case below
  // — an unauthenticated caller is never "still loading", it has a definite answer already.
  if (!isDevBypass && authChecked && !bearerToken) {
    return (
      <SignInScreen
        marking={deploymentMarking()}
        reason={signInReason}
        intent={handoff.view}
        welcome={deploymentWelcome()}
        onSignIn={(organisationProvider) => void signIn(organisationProvider)}
      />
    );
  }

  // ADR-050 Amendment 1: over whichever screen is shown, so that screen is kept as it is.
  const sessionPromptShown =
    sessionPrompt !== null && bearerToken ? (
      <SessionPrompt
        why={sessionPrompt}
        busy={sessionPromptBusy}
        problem={sessionPromptProblem}
        onSignInAgain={() => void signInAgain()}
        onTryAgain={tryRenewingAgain}
      />
    ) : null;

  // ADR-145 decision 11 (A2), L2.7: *Needs you*, before the account wherever the account is shown. An
  // overdue promotion opens Admin › Operations for a reader who holds `operate_schedules`; proposed
  // link types open the Studio's Model tab on their dataset, through a case of the reader's that
  // loads into it (`ingest/studio/datasets.ts`), as the Studio's own switcher does.
  const openModelFor = async (datasetId: string): Promise<void> => {
    requestOpening({ kind: "studio", tab: "model", datasetId });
    let cases;
    try {
      cases = await listCases(API_BASE_URL, bearerToken ?? "");
    } catch {
      takeOpening("studio");
      throw new Error("Your cases could not be read, so the Studio was not opened. Try again.");
    }
    const caseId = caseForDataset(cases, datasetId, investigationId);
    if (!caseId) {
      takeOpening("studio"); // no case of theirs loads into it now: nothing to open
      throw new Error("None of your cases loads into that dataset now, so the Studio cannot open on it.");
    }
    if (caseId === investigationId) {
      setStartChoice(null);
      setView("ingest");
    } else {
      openCase(caseId, "ingest");
    }
  };
  const openOperations = () => {
    requestOpening({ kind: "admin", section: "operations" });
    setStartChoice("admin");
  };
  // ADR-145 Amendment 4 decision 12 (L2.7): Home's *Your access and tasks* (Amendment 11).
  const answers =
    bearerToken && rights ? (
      <AnswersForSection
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        rights={rights}
        roles={principal?.roles ?? []}
        onOpenCase={(id) => openCase(id)}
        onOpenModel={rights.has("accept_types") ? openModelFor : undefined}
        onOpenOperations={rights.has("operate_schedules") ? openOperations : undefined}
      />
    ) : null;
  const needsYou = bearerToken ? (
    <NeedsYou
      apiBaseUrl={API_BASE_URL}
      bearerToken={bearerToken}
      onOpenModel={rights?.has("accept_types") ? openModelFor : undefined}
      onOpenOperations={rights?.has("operate_schedules") ? openOperations : undefined}
    />
  ) : null;
  // ADR-148 Amendment 8: without a resolved principal nothing is offered, but the person is never
  // left without words or a way out.
  const accountUnread =
    !isDevBypass && !principal && resolvedFailed ? (
      <AccountUnread onTryAgain={() => setResolvedAttempt((n) => n + 1)} onSignOut={() => void signOut()} />
    ) : null;
  const account = (
    <>
      {needsYou}
      {!isDevBypass && principal ? <AccountMenu principal={principal} onSignOut={() => void signOut()} /> : accountUnread}
    </>
  );
  const startScreenShown =
    isDevBypass || bearerToken
      ? startScreen({
          rights,
          rightsSettled: isDevBypass || rightsSettled,
          investigationId,
          startChoice,
          setStartChoice,
          account,
          marking: deploymentMarking(),
          person: {
            username: principal?.username ?? "",
            givenName: principal?.givenName ?? null,
            clearance: principal?.clearance ?? "",
            roles: principal?.roles ?? [],
          },
          summary: homeSummary,
          apiBaseUrl: API_BASE_URL,
          bearerToken,
          lastCaseId: investigationIdFromSession(),
          isAdministrator: principal?.roles?.includes("osprey-admin") ?? false,
          openCase,
          browseCases: () => setBrowsingCases(true),
          openStudio: () => setView("ingest"),
          openRules: () => setView("alerts"),
          openAlert: (alertId) => navigate(alertPath(alertId)),
          openCaseOnRules: (id) => openRulesOnCase(id),
          answers,
          openAlertJourney: (alert, to) =>
            startJourney({ to, caseId: alert.caseId, alertId: alert.alertId, title: alert.title, rule: alert.rule, weeks: weeksFor(alert.at) }),
        })
      : null;
  if (startScreenShown)
    return (
      <>
        {startScreenShown}
        {sessionPromptShown}
      </>
    );

  if (browsingCases && (isDevBypass || bearerToken)) {
    return (
      <>
        <CasePicker
          openCaseId={investigationId}
          onClose={investigationId ? () => setBrowsingCases(false) : undefined}
          onStart={() => {
            setBrowsingCases(false);
            setStartChoice("start");
          }}
          apiBaseUrl={API_BASE_URL}
          bearerToken={bearerToken}
          lastCaseId={investigationIdFromSession()}
          isAdministrator={principal?.roles?.includes("osprey-admin") ?? false}
          // The gate is also where the Studio tile's arrival lands when no case is open yet: the
          // reload it causes must keep that choice, or the tile opens the Glass (seen 10 Oct 2026).
          onOpen={(id) => openCase(id, view === "ingest" ? "ingest" : undefined)}
        />
        {sessionPromptShown}
      </>
    );
  }

  if (!investigationId || !ontology || !crossFilterRef.current) {
    return (
      <>
        <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>Loading…</div>
        {sessionPromptShown}
      </>
    );
  }
  const crossFilterStore = crossFilterRef.current;
  // The timeline and the status line describe the working set: they belong beside the graph and
  // the map, not over Reports, a Superset board or the Admin area, and not to an account that may
  // not investigate (opened under an embedded board, the timeline overlapped it).
  // ADR-097 step 1: the rail's panel openers inside the Glass (ADR-145 Amendment 15: the panels alone; the views are
  // the top bar's view switch).
  // ADR-145 Amendment 12: where the keys panel is, and whether it is shown at all. The graph, the
  // map and the matrix share the canvas area, under whose toolbar it sits, as before; any other view
  // has it in the column the views share.
  const inCanvasArea = !["ingest", "dossier", "alerts", "strength", "ownership", "reports", "dashboards", "boards"].includes(view);
  const welcomeOpen = app === "glass" && (welcome === "asked" || (welcome === "auto" && view === "graph" && !lens));
  closeWelcomeRef.current = () => {
    setWelcome("closed");
    // Closed once, by any of its ways (×, Esc, Help or `?` again), it stays closed at sign-in.
    if (principal?.sub) setWelcomeDismissed(principal.sub, true);
  };
  shownWelcomeRef.current = welcomeOpen;
  helpHereRef.current = app === "glass";
  const welcomePanel = (
    <WorkspaceWelcome
      apiBaseUrl={API_BASE_URL}
      bearerToken={bearerToken}
      investigationId={investigationId}
      nodeCount={counts.nodes}
      onRestored={(snapshot) =>
        applyRestoredSnapshot(workingSetRef.current.store, resyncFromNothing, snapshot)
      }
      onClose={() => closeWelcomeRef.current()}
      // Asked for by Help or `?`, it takes focus, so Esc closes it at once.
      takeFocus={welcome === "asked"}
      // The user guide, as Home's Glass card links it (ADR-145 Amendment 10); the route checks
      // the person's rights itself.
      guide={{
        href: guideUrl(API_BASE_URL, "user"),
        open: () => openGuide("user", { apiBaseUrl: API_BASE_URL, bearerToken }),
      }}
    />
  );
  // The owner's navigation decision of 13 November 2026 (ADR-145 Amendment 15, amending Amendments 2 and 12): the
  // rail holds the panel openers alone, Explore, Ask & Chat and History (`shell/railLayout.ts`), each toggling its
  // panel and marked expanded while it is open, never pressed (`railMark`); opening or closing one never changes
  // the view.
  const railOpen = new Set<RailEntry>(
    ([["explore", exploreOpen], ["questions", questionsOpen], ["history", historyOpen]] as const)
      .filter(([, open]) => open)
      .map(([id]) => id),
  );
  const mark = (id: RailEntry) => railMark(id, { view, open: railOpen });
  const railTools = [
    { id: "explore", label: RAIL_LABELS.explore, icon: "explore" as const, onSelect: () => setExploreOpen((open) => !open), ...mark("explore") },
    { id: "questions", label: RAIL_LABELS.questions, icon: "questions" as const, onSelect: () => setQuestionsOpen((open) => !open), ...mark("questions") },
    { id: "history", label: RAIL_LABELS.history, icon: "history" as const, onSelect: () => setHistoryOpen((open) => !open), ...mark("history") },
  ].filter((entry) => (railEntries(rights) as string[]).includes(entry.id));
  const railSplit = splitRail(railTools);
  // Amendment 15: one view switch in the top bar, Graph · Map · Drawing board · Reports, then More views with Matrix,
  // Figures, Ownership and Connection strength; exactly one view is current. *Reports* is ADR-111 Amendment 3's
  // dashboards view, unchanged inside. Someone offered none of the four (the built-in Administrator, offered Connection
  // strength alone) has theirs in the switch itself. What is offered is `offeredViews`, which the harnesses read too.
  const reportsUrl = deploymentReportsUrl();
  const { main: mainViews, more: otherViews } = splitViews(
    offeredViews(rights)
      .map((id) => ({
        id,
        label: VIEW_LABELS[id],
        // Part A: while the search results show, no view is current, and choosing any view leaves them.
        pressed: view === id && searching === null,
        onSelect:
          id === "boards"
            ? () => {
                setSearching(null);
                setBoardToOpen(null);
                setView("boards");
              }
            : () => {
                setSearching(null);
                setView(id);
              },
      })),
  );
  const showsWorkingSetTools =
    // Rules and Monitoring is a place of its own (ADR-146 decision 2), not a view over the working set.
    showsInspector(rights) && !["ingest", "alerts", "dossier", "reports", "dashboards"].includes(view);

  return (
    // ADR-132: the window less whatever the brand frame shows above (`brand/BrandFrame.tsx`).
    <div style={{ display: "flex", flexDirection: "column", height: "var(--workspace-height, 100vh)" }}>
      {/* ADR-097 step 1 (design review item 16): the protective marking of what is on screen. */}
      <ClassificationStrip marking={marking} />
      <TopBar
        app={app}
        onStart={() => setStartChoice("start")}
        // ADR-145 decision 1: the places this person's rights open (inside the GOV.UK header under
        // that brand). Admin is a place of its own, outside the case.
        places={
          <PlaceSwitcher
            places={startPlaces(rights)}
            current={app}
            counts={{ rules: alertCount }}
            onChoose={(place) => {
              if (place === "admin") setStartChoice("admin");
              else if (place === "ingest") setView("ingest");
              else if (place === "rules") setView("alerts");
              else if (app !== "glass") setView(lastGlassView());
              // Rules and Monitoring's addresses are its own: another place leaves them.
              if (place !== "rules" && address.kind !== "none") navigate("/");
            }}
          />
        }
        search={
          app === "glass" ? (
            <GlobalSearch
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationId={investigationId}
              entityTypes={ontologySchema?.entity_types.map((e) => e.name) ?? []}
              onApplyDelta={applyStarterDelta}
              // Part A: Enter on the typed words opens the results page over the view on screen.
              onSearch={(query) =>
                setSearching({ query, left: view === "dossier" ? "Messages" : (VIEW_LABELS as Record<string, string>)[view] ?? "Graph" })
              }
              screenNodes={() => {
                const graph = workingSetRef.current.graph;
                return graph.nodes().map((id) => graph.getNodeAttribute(id, "data"));
              }}
              onSelect={(node) => {
                void drawSearchResult(
                  (nodes) => seedToCanvas(nodes, []),
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
                ...(mainViews.length > 0 ? mainViews : otherViews),
                ...(dossierNodeId
                  ? [{ id: "dossier", label: "Messages", pressed: view === "dossier" && searching === null, onSelect: () => {
                      setSearching(null);
                      setView("dossier");
                    } }]
                  : []),
              ]
            : []
        }
        moreViews={app === "glass" && mainViews.length > 0 ? otherViews : []}
        // The owner's ruling of 13 November 2026 (Q2; ADR-145 Amendment 15): *Build a report* beside Reports, opening
        // Superset (the deployment's `bi.` address) in a new tab, for a holder of manage_dashboards where Superset is
        // deployed. Superset refuses anyone else; the link is offered to no one else.
        besideViews={
          app === "glass" && reportsUrl && rights?.has("manage_dashboards") ? <BuildAReportLink href={reportsUrl} /> : undefined
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
            {needsYou}
            {!isDevBypass && principal && (
              // `06_DECISIONS.md` ADR-050: the principal's identity and clearance are shown in the
              // chrome, informationally only. ADR-065 folds the subject, unit and Sign out behind one
              // button that keeps the clearance in view. The Glass derives nothing from any of it.
              <AccountMenu principal={principal} onSignOut={() => void signOut()} />
            )}
            {accountUnread}
          </>
        }
      />
      {/* ADR-145 decision 2: one line naming the place, the case and what it reads, with the
          cross-link between the Glass and the Studio for a person who holds both. */}
      <ContextBanner
        place={app}
        // The owner's navigation decision (ADR-145 Amendment 15): no mode toggle and no note in the Glass; its views
        // are the top bar's one switch. The case line's *Views in this case* opens the Cases panel at its views.
        onViews={app === "glass" ? () => setCasesOpen((open) => (open ? false : "views")) : undefined}
        viewsOpen={casesOpen !== false}
        caseSwitcher={
          <CaseSwitcher
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            currentId={investigationId}
            // Amendment 15: in the Glass the menu's last entry, *All cases*, opens the Cases panel (its *Browse all
            // cases* the full list). In the Studio and in Rules and Monitoring it opens the case picker as before, whose
            // choice keeps the place (seen 10 Oct 2026; the lane-reviewer's item 1): the panel is the Glass's.
            onBrowse={app === "glass" ? () => setCasesOpen("all") : () => setBrowsingCases(true)}
            onOpen={(id) => openCase(id, view === "ingest" ? "ingest" : undefined)}
            // ADR-145 Amendment 14 decision 4: where the Glass's banner says what the case reads ("reads …", or
            // "reads no dataset"), the switcher's scope badge (ADR-115 Amendment 1 point 5) would say it again;
            // while the case's datasets are read or refused the banner says nothing, and the badge stays.
            showScope={!(app === "glass" && caseContext.datasets !== null)}
          />
        }
        // ADR-145 decision 2: the Glass names what the case reads; the Studio's dataset is its own
        // choice, drawn by the Studio (`ingest/IngestStudio.tsx`), so the banner does not repeat it.
        datasets={app === "glass" ? caseContext.datasets : null}
        crossLink={crossLinkFor(app, startPlaces(rights), caseContext.name, caseContext.datasets, {
          toStudio: () => setView("ingest"),
          toGlass: () => setView(lastGlassView()),
        })}
      />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      {/* ADR-097 step 1: the left rail, the Glass's alone (ADR-145 decision 1); the Studio has none. */}
      {app === "glass" && (
      <LeftRail
        // ADR-145 Amendment 15: the panel openers alone (Explore, Ask & Chat, History), then Help and
        // Show names; the views are the top bar's view switch, and Cases is reached from the case line.
        items={railSplit.items}
        more={railSplit.more}
        onHelp={toggleWelcome}
      />
      )}
      {/* `position: relative` so the keys panel, over whichever view is on screen, is placed in it. */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, position: "relative" }}>
      {/* Part A: the view left stays as it was beneath the search results, out of reach while they show. */}
      <div style={{ display: "contents" }} inert={app === "glass" && searching !== null && readerDocumentId === null ? true : undefined}>
      {/* ADR-145 Amendment 12: the keys panel over any view the view switch opens, not only the graph's
          (it was drawn beside the graph alone, so Help did nothing visible elsewhere). */}
      {welcomeOpen && !inCanvasArea && welcomePanel}
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
            rights={rights}
            username={principal?.username || null}
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
        {view === "alerts" && (
          <RulesPlace
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            accountId={principal?.sub ?? null}
            isAdministrator={principal?.roles?.includes("osprey-admin") ?? false}
            canManageLists={rights?.has("load_screening_lists") ?? false}
            canMakeLive={rights?.has("deploy_rules") ?? false}
            onCanvas={(outcome, nodeIds) => {
              applyStarterDelta(outcome.delta);
              pendingHighlight.current = nodeIds;
              setView("graph");
            }}
            address={addressedAlert && addressed ? { alertId: addressedAlert, state: addressed } : null}
            onOpenAlert={(alertId) => navigate(alertId ? alertPath(alertId) : "/")}
            // L3.6: *Open the board* from a drawn watch's alert, on this case's Drawing board.
            onOpenBoard={(boardId) => {
              setBoardToOpen(boardId);
              setView("boards");
            }}
            // ADR-146 decision 6 (R5): the alert's evidence as a private view of its case (ADR-144
            // decision 4), opened as the Glass's read-only lens, with the way back to the alert.
            onOpenEvidence={async ({ alertId, title, nodeIds, caseId }) => {
              // Saved into the alert's own case, and refused in words if that is not the case open.
              const into = evidenceCase(
                { alertId, caseId },
                investigationId,
                addressedAlert && addressed ? { alertId: addressedAlert, state: addressed } : null,
              );
              if ("refused" in into) return into.refused;
              const saved = await saveView(API_BASE_URL, bearerToken, into.caseId, {
                name: `From alert: ${title}`.slice(0, 200),
                nodeIds,
              });
              if (!saved.ok) return saved.message;
              // Said on the alert, which stays open at its address, when the view cannot be opened.
              const problem = await openLens(saved.view.id, { alertId, title });
              // Said there alone: the Glass, visited next, must not carry it over its canvas.
              if (problem) {
                setViewProblem(null);
                return `The evidence was saved as the private view “${saved.view.name}”, but it could not be opened: ${problem}`;
              }
              navigate("/");
              return null;
            }}
          />
        )}
        {view === "strength" && investigationId && (
          // ADR-139: what makes a link strong in this case, and who may change it.
          <section aria-label="Connection strength" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}>
            <h2 className="value" style={{ margin: 0 }}>Connection strength</h2>
            <StrengthPanel
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              investigationId={investigationId}
              accountId={principal?.sub ?? null}
              canManage={rights?.has("manage_strength_influencers") ?? false}
              entityTypes={ontologySchema?.entity_types ?? []}
              edgeTypes={edgeTypes}
              onChanged={() => setStrengthRead((n) => n + 1)}
            />
          </section>
        )}
        {view === "reports" && (
          <ReportsPlace key={reportsStart.opened} initialTab={reportsStart.tab} apiBaseUrl={API_BASE_URL} bearerToken={bearerToken} investigationId={investigationId} canDownload={canDownloadFeed(rights)} rights={rights}
                        onOpenAlert={openAlertFromPanel} fromAlert={alertJourney?.to === "figures" ? journeyBack : null}
                        initialWeeks={alertJourney?.to === "figures" ? alertJourney.weeks : undefined} />
        )}
        {view === "dashboards" && (
          <div style={{ flex: 1, display: "flex", padding: "var(--sp-16)", minHeight: 0 }}>
            <EmbeddedDashboards apiBaseUrl={API_BASE_URL} bearerToken={bearerToken}
              // ADR-145 Amendment 4 decision 9: the Alert monitoring board, first, on the open case.
              leading={investigationId ? { ...ALERT_MONITORING, draw: () => (
                <AlertMonitoringBoard key={alertJourney?.alertId ?? "board"} api={{ apiBaseUrl: API_BASE_URL, bearerToken, investigationId }}
                  onOpenAlert={openAlertFromPanel} fromAlert={alertJourney?.to === "board" ? journeyBack : null}
                  filter={alertJourney?.to === "board" ? { rule: alertJourney.rule, weeks: alertJourney.weeks } : undefined} />
              ) } : undefined} />
          </div>
        )}
        {view === "ownership" && (
          <OwnershipPlace
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            onCanvas={(outcome, nodeIds) => {
              applyStarterDelta(outcome.delta);
              pendingHighlight.current = nodeIds;
              setView("graph");
            }}
          />
        )}
        {view === "boards" && (
          <BoardsPlace
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            caseId={investigationId}
            caseName={caseContext.name}
            selection={selectedNodeIds}
            entityTypes={ontologySchema?.entity_types ?? []}
            markings={classificationOrder}
            mayDraw={(rights?.has("draw_on_boards") && rights?.has("investigate")) ?? false}
            initialBoard={boardToOpen}
            onCaseMade={(newInvestigationId, boardId) => {
              sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, newInvestigationId);
              setInvestigationId(newInvestigationId);
              setBoardToOpen(boardId);
            }}
          />
        )}
        {view !== "ingest" && view !== "dossier" && view !== "alerts" && view !== "strength" && view !== "ownership" && view !== "reports" && view !== "dashboards" && view !== "boards" && (
          <div style={{ flex: 1, position: "relative" }}>
            {view === "graph" && lens && (
              <ViewLensBanner
                name={lens.opened.view.name}
                shared={lens.opened.view.shared ?? false}
                missing={lens.opened.missing}
                annotations={lens.opened.annotations ?? []}
                onBack={closeLens}
                from={
                  lensFromAlert
                    ? {
                        label: "Opened from an alert",
                        backLabel: "← Back to the alert",
                        onBack: () => {
                          const { alertId } = lensFromAlert;
                          closeLens();
                          navigate(alertPath(alertId));
                        },
                      }
                    : undefined
                }
              />
            )}
            {view === "graph" && viewProblem && (
              <p role="alert" className="view-lens-banner">
                {viewProblem}
              </p>
            )}
            {/* ADR-145 Amendment 12: the keys panel under the canvas toolbar, on the graph, the map and the
                matrix alike; any other view has it in the column (above). */}
            {welcomeOpen && welcomePanel}
            {view === "graph" && (
              <GlassCanvas
                // A view opened or closed draws a different working set: the canvas starts afresh.
                key={lens ? `view:${lens.opened.view.id}` : "case"}
                ref={glassCanvasRef}
                lastChange={lastChange}
                graph={(lens?.workingSet ?? workingSetRef.current).graph}
                store={(lens?.workingSet ?? workingSetRef.current).store}
                ontology={ontology}
                edgeTypes={edgeTypes}
                entityTypes={ontologySchema?.entity_types}
                investigationId={investigationId}
                apiBaseUrl={API_BASE_URL}
                bearerToken={bearerToken}
                dimmedNodeIds={dimmedNodeIds}
                dimmedEdgeIds={dimmedEdgeIds}
                strengthLegend={strengthLegend}
                onGroupedCountChange={setGroupedCount}
                judgementCounts={judgementCounts}
                alertBadges={alertBadges}
                degreeMarks={degreeMarks}
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
                onViewSaved={() => setViewsRead((n) => n + 1)}
                onAskInView={(saved) => {
                  setViewsRead((n) => n + 1);
                  setQuestionsView({ id: saved.id, name: saved.name });
                  setQuestionsOpen(true);
                }}
                lens={lens !== null}
                // ADR-144 Amendment 3: the case's saved views one click from the canvas; opening one is
                // the drawer's own `openLens`.
                viewsMenu={
                  investigationId ? (
                    <ViewsMenu
                      apiBaseUrl={API_BASE_URL}
                      bearerToken={bearerToken}
                      caseId={investigationId}
                      openViewId={lens?.opened.view.id ?? null}
                      onOpen={(chosen) => void openLens(chosen.id)}
                    />
                  ) : undefined
                }
                onSelectionChange={(nodeIds) => {
                  setSelectedNodeIds(nodeIds);
                  const first = nodeIds[0];
                  const graph = (lens?.workingSet ?? workingSetRef.current).graph;
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
                onSetPicture={() => setPictureOpenSignal((n) => n + 1)}
                // §2 rule 1: switching view never loses selection — the Matrix's, or what was
                // selected before the Map opened, is the canvas's when it is drawn again.
                initialSelectedNodeIds={selectedNodeIds}
                initialSelectedEdgeId={selectedLink?.id ?? null}
              />
            )}
            {view === "matrix" && (
              <MatrixView
                graph={workingSetRef.current.graph}
                store={workingSetRef.current.store}
                edgeTypes={edgeTypes}
                visualFor={(type) => ontology.visualFor(type)}
                dimmedNodeIds={dimmedNodeIds}
                dimmedEdgeIds={dimmedEdgeIds}
                selectedNodeIds={selectedNodeIds}
                selectedEdgeId={selectedLink?.id ?? null}
                onSelectNodes={selectNodesOffCanvas}
                onSelectLink={selectLinkOffCanvas}
                onExpand={expandOnGraph}
                onShowOnGraph={showOnGraph}
                strength={
                  investigationId ? { apiBaseUrl: API_BASE_URL, bearerToken, investigationId } : undefined
                }
              />
            )}
            {/* ADR-100: an empty canvas offers where to start, until something is drawn. */}
            {view === "graph" && counts.nodes === 0 && investigationId && !lens && (
              <div
                className="explore-overlay"
                style={{
                  position: "absolute",
                  top: "var(--sp-40)",
                  // Beside the welcome panel when it is open, never under it.
                  ...exploreOverlayPlace(welcomeOpen),
                  transform: "translateX(-50%)",
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
                  onAddLinks={addWithBusiest}
                  onExpandAll={expandAllOf}
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
                      // P4: the basemap switch and the place search over the case's gazetteer.
                      providers={switchableProviders(mapConfig)}
                      searchPlaces={
                        investigationId
                          ? (query) =>
                              searchPlaces(API_BASE_URL, bearerToken, investigationId, query)
                          : undefined
                      }
                      gazetteers={gazetteerControls}
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
                    {hotspotEdgeTypes.length > 0 && (
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
                        locationEdgeTypes={hotspotEdgeTypes}
                      />
                    </div>
                    )}
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
        {view !== "ingest" && view !== "alerts" && view !== "dossier" && view !== "dashboards" && showsInspector(rights) && (
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
                      // ADR-115 E4: the Inspector's Expand, through the canvas's own preview.
                      // With no canvas drawn (the Matrix, the Map), the Graph opens and expands it.
                      onExpand={(id) => (glassCanvasRef.current ? glassCanvasRef.current.expandNode(id) : expandOnGraph(id))}
                      // ADR-097 step 1: several selected are shown together (the list of ADR-093
                      // is one of their parts), not the first alone.
                      selection={{
                        nodes: selectedNodeIds
                          .filter((id) => workingSetRef.current.graph.hasNode(id))
                          .map((id) => workingSetRef.current.graph.getNodeAttribute(id, "data")),
                        onCentre: (id) => (glassCanvasRef.current ? glassCanvasRef.current.centreOn(id) : showOnGraph(id)),
                        onRemove: (id) =>
                          glassCanvasRef.current
                            ? glassCanvasRef.current.deselect(id)
                            : selectNodesOffCanvas(selectedNodeIds.filter((n) => n !== id)),
                      }}
                      visualFor={(type) => ontology.visualFor(type)}
                      neighbourhoodRisk={
                        investigationId
                          ? { apiBaseUrl: API_BASE_URL, bearerToken, investigationId }
                          : undefined
                      }
                      watch={
                        investigationId && canKeepWatches(rights)
                          ? { apiBaseUrl: API_BASE_URL, bearerToken, investigationId }
                          : undefined
                      }
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
                      openPictureSignal={pictureOpenSignal}
                      picture={
                        ontologySchema && pictureTypes.size > 0
                          ? {
                              apiBaseUrl: API_BASE_URL,
                              bearerToken,
                              investigationId,
                              types: pictureTypes,
                              onDelta: (delta) => applyStarterDelta(delta as WorkingSetDelta),
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
                            selectedNodeIds={selectedNodeIds}
                            canKeepWatches={canKeepWatches(rights)}
                            canRaiseAlerts={canRaiseAlerts(rights)}
                          />
                        ),
                      },
                    ]
                  : []),
                ...(view === "graph" && investigationId
                  ? [
                      {
                        id: "connections" as const,
                        name: "Find connections",
                        content: (
                          <FindConnectionsPanel
                            apiBaseUrl={API_BASE_URL}
                            bearerToken={bearerToken}
                            investigationId={investigationId}
                            selected={selectedNode}
                            canvas={workingSetRef.current.graph}
                            onDelta={(delta) => workingSetRef.current.store.getState().applyDelta(delta)}
                            onMark={(marks) => setDegreeMarks((prev) => new Map([...prev, ...marks]))}
                            onClearMarks={() => setDegreeMarks(new Map())}
                            edgeTypes={edgeTypes}
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
      {showsWorkingSetTools && (
        // ADR-097 step 1: folded to its header by default, so the canvas has the room; opened and
        // sized as before (ADR-086).
        <BottomPanelFrame
          title="Timeline"
          height={DEFAULT_TIMELINE_HEIGHT}
          initiallyOpen={false}
          openSignal={timelineOpenSignal}
          summary={<TimelineStrip />}
        >
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
              // ADR-128 decision 2 (B3): offered only while the canvas is the view on screen.
              onSelectLit={
                view === "graph"
                  ? () => {
                      const { window: lit, cells } = crossFilterStore.store.getState();
                      if (lit) void glassCanvasRef.current?.selectLit(lit, cells);
                    }
                  : undefined
              }
            />
          </div>
        </BottomPanelFrame>
      )}
      </div>
      {/* Part A: the results fill the main area, over the view left, hidden (kept) while a document is read from them. */}
      {app === "glass" && searching !== null && investigationId && bearerToken && (
        <SearchResults
          key={searching.query}
          hidden={readerDocumentId !== null}
          apiBaseUrl={API_BASE_URL}
          bearerToken={bearerToken}
          investigationId={investigationId}
          query={searching.query}
          backLabel={searching.left}
          onBack={() => {
            focusSearchBox.current = true;
            setSearching(null);
          }}
          onShow={(nodes) => {
            void seedToCanvas(nodes, []);
            setSelectedNode(nodes[0] ?? null);
            setSearching(null);
            setView("graph");
          }}
          onOpenDocument={(id) => {
            setReaderFallback(undefined);
            setReaderDocumentId(id);
          }}
          onAsk={railEntries(rights).includes("questions") ? (words) => {
            setQuestionDraft({ text: words, at: Date.now() });
            setQuestionsOpen(true);
          } : undefined}
        />
      )}
      </div>
      </div>
      {showsWorkingSetTools && (
        <StatusBar
          nodeCount={counts.nodes}
          edgeCount={counts.edges}
          dimmedCount={dimmedNodeIds.size}
          withheld={withheld}
          groupedCount={groupedCount}
        />
      )}
      {bearerToken && investigationId && (
        <ViewOverCapGate
          store={workingSetRef.current.store}
          requestResync={resyncFromNothing}
          entityTypes={ontologySchema?.entity_types.map((e) => e.name) ?? []}
          apiBaseUrl={API_BASE_URL}
          bearerToken={bearerToken}
          investigationId={investigationId}
          onViewOpened={(opened) => {
            setViewsRead((n) => n + 1);
            showLens(opened);
          }}
          // The lens is the Graph's: on the Map or the Matrix the case is on screen, and so is its cap.
          lensOpen={lens !== null && view === "graph"}
        />
      )}
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
            onAddLinks={(node, links) => {
              addWithBusiest(node, links);
              setExploreOpen(false);
            }}
            onExpandAll={(node) => {
              expandAllOf(node);
              setExploreOpen(false);
            }}
          />
        )}
      </Drawer>
      <Drawer open={questionsOpen} onClose={() => setQuestionsOpen(false)} title={RAIL_LABELS.questions}>
        <QuestionsPanel
          apiBaseUrl={API_BASE_URL}
          bearerToken={bearerToken}
          investigationId={investigationId}
          onDelta={(delta) => workingSetRef.current.store.getState().applyDelta(delta as WorkingSetDelta)}
          onOpenDocument={(id) => {
            setReaderFallback(undefined);
            setReaderDocumentId(id);
          }}
          // ADR-129: the graph facts asked about are what is selected and one link around it, and
          // inside the timeline window when one is set; a `[G-n]` chosen in an answer selects what
          // it stands for on the canvas and brings it into view.
          selection={{
            nodeIds: selectedNodeIds,
            linkIds: selectedLink ? [selectedLink.id] : [],
          }}
          getTimelineWindow={() => crossFilterRef.current?.store.getState().window ?? null}
          onSelectFacts={(citation) => {
            if (glassCanvasRef.current) bringFactIntoView(glassCanvasRef.current, citation);
          }}
          view={questionsView}
          onLeaveView={() => setQuestionsView(null)}
          draft={questionDraft}
        />
      </Drawer>
      {/* ADR-144 decision 5: the open case's *Views in this case*, then every case once with its views. */}
      <Drawer
        open={casesOpen !== false}
        onClose={() => setCasesOpen(false)}
        title="Cases"
        // Opened from the case menu's *All cases*, whose item went with its menu: focus goes back to the menu's button.
        returnFocusTo={() => document.querySelector<HTMLElement>("[aria-labelledby='context-banner-title'] .menu-button--case")}
      >
        <div className="drawer-stack">
          {investigationId && (
            <ViewsPanel
              apiBaseUrl={API_BASE_URL}
              bearerToken={bearerToken}
              caseId={investigationId}
              me={principal?.sub ?? ""}
              openViewId={lens?.opened.view.id ?? null}
              refreshKey={viewsRead}
              takeFocus={casesOpen === "views"}
              onOpen={(chosen) => {
                setCasesOpen(false);
                void openLens(chosen.id);
              }}
              onDeleted={(viewId) => {
                setViewsRead((n) => n + 1);
                if (lens?.opened.view.id === viewId) closeLens();
                if (questionsView?.id === viewId) setQuestionsView(null);
              }}
            />
          )}
          <CaseList
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            currentId={investigationId}
            refreshKey={viewsRead}
            onOpen={(id) => {
              setCasesOpen(false);
              openCase(id);
            }}
            onOpenView={(caseId, chosen: CaseView) => {
              setCasesOpen(false);
              if (caseId === investigationId) void openLens(chosen.id);
              else openCaseView(caseId, chosen.id);
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
          {/* ADR-128 decision 3: the case's brief, read by anyone who may read the case and edited by
              its Author; an attachment opens where the thing lives. */}
          <CaseBrief
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            rights={rights}
            onOpenAttachment={openBriefAttachment}
          />
          {/* ADR-099, ADR-126: what the open case reads and its domain models, changed by its Author
              (who holds `share_case`); the listing is read once for both. */}
          <CaseSettings
            apiBaseUrl={API_BASE_URL}
            bearerToken={bearerToken}
            investigationId={investigationId}
            rights={rights}
            onChanged={() => window.location.reload()}
          />
          {/* ADR-052 §9: who can open the case — its Author gives and removes levels. */}
          <CaseAccessPanel apiBaseUrl={API_BASE_URL} bearerToken={bearerToken} investigationId={investigationId} />
        </div>
      </Drawer>
      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        investigationId={investigationId}
        apiBaseUrl={API_BASE_URL}
        bearerToken={bearerToken}
        onRestored={(snapshot) =>
          applyRestoredSnapshot(workingSetRef.current.store, resyncFromNothing, snapshot)
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
      {sessionPromptShown}
    </div>
  );
}
