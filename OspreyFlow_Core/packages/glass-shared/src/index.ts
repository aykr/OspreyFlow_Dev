// The Glass's plain TypeScript, kept once for both front ends (ADR-152 decision 6): logic, stores, the panel
// pattern, the Conduit client, the keyboard action registry, structural types for the map and graph.
//
// What is here so far (slices PL4 C to E move the React workspace's plain leaves in, one behaviour-preserving
// change at a time, invariant I11; each adds its exports below):
//   keyboard/actionRegistry   the keyboard action registry: data, `defineActionRegistry`, `registerCovered`,
//                             `assertAllCovered`
//   workingset/store, models  the working set's store (graphology and `zustand/vanilla`) and its typed deltas
//   color/textContrast        the text-contrast judgement the accessibility probe runs in Node
//   map/contrast              the WCAG contrast ratio of two colours
//   map/conduitRequest        which of MapLibre's tile reads carry the bearer token (a request transform: it
//                             imports nothing from the map library)
//   theme/theme, brand/brand  light and dark, and the deployment's brand (ADR-070, ADR-132): the choice, its cookie,
//                             what a canvas asks to draw again (PL4 slice D1; the toggle button stays in the workspace)
//   color/palette, tokens, oklab, nodeGlyphs
//                             the canvas's colours by theme, the token mirrors, the OKLab arithmetic, the node glyphs
//   welcome/statement         what the product is, worded once (ADR-034 Amendment 1)
//   layout/layoutSizes, panelOrder, sidePanelState, panelFrameStore, panelFrameAttach
//                             the sizes, the panel order and the side panel's mode, kept in this browser: the plain
//                             halves (the React hooks over them stay in the workspace's files of the same names); the
//                             store that holds them with the fold and the ten panel actions, and its attach point
//   admin/inviter             what an inviter may give: the types and `givableLevels`, `givableCodes` (the context and
//                             `useInviter` stay in the workspace)
//   ingest/api, ingest/sources/api, ingest/releases/releasesApi
//                             the Conduit clients of the Ingest Studio, the registered sources and the releases
//   admin/sections/MapsApi, ModelsApi, admin/updateNotice
//                             the Conduit clients of Admin's maps and models, and the update notice's words
//                             (PL4 slice D2: each calls `fetch` and takes the bearer token as an argument; `admin/api`
//                             stays in the workspace for now, because it takes its words about a refusal from
//                             `help/roles`, which reads a record the workspace holds)
//   export/withheldSentence, export/api, alerts/api, alerts/names, alerts/closingReasons, patterns/api,
//   models/modelDeadline, reports/api, caseHttp, dashboards, trendsApi, packsApi, packText
//                             the Conduit clients of the export, the alert queue and rules, the patterns and the reports,
//                             and the words they and the print document share (PL4 slice D3a: each calls `fetch` and takes
//                             the bearer token as an argument; `WITHHELD_SENTENCE` came out of the status bar's React file)
//   inspector/emailDocuments, linkChangeApi, linkEventsApi, linkNotesApi, linktypes/http, linkTypesApi,
//   modelProposalsApi, questions/questionsApi, graphFacts, reader/readerApi, dossier/api, models,
//   views/viewsApi, workingset/batchExpansionApi, boards/promotionsApi, analytics/api
//                             the Conduit clients of the link inspector and its notes, the link types and their model
//                             proposals, the questions and the reader, the saved views, the batch expansion, the boards'
//                             promotions and the analytics (PL4 slice D3b: each calls `fetch` and takes the bearer token
//                             as an argument; `questions/graphFacts` came along, as `questionsApi` takes its citation
//                             types from it). Three names were written twice, so the index gives them apart: the link
//                             types' `send` is `sendLinkType`, the promotions' is `sendPromotion` and the questions'
//                             `rejectProposal` is `rejectQuestionProposal` (the report clients keep `send`)
//   assessment/api, boards/boardsApi, connections/connectionsApi, explore/exploreApi, map/providers, metrics/api,
//   ownership/api, search/addFromListApi, site/api, site/bilinear, strength/api, watches/api
//                             the remaining plain Conduit clients: the assessment's judgements, assumptions and gaps, the
//                             boards, the connections, the exploring panel, the map's provider list, the metrics call,
//                             the ownership place, the list-adding call, the site calibration's call and arithmetic, the
//                             strength explainer and the watches (PL4 slice D3c: each calls `fetch` and takes the bearer
//                             token as an argument). Two names were written twice, so the index gives them apart: the
//                             assessment's `listJudgements` is `listAssessmentJudgements` (the report clients keep
//                             `listJudgements`) and the boards' `Answer` is `BoardAnswer` (the promotions keep `Answer`)
//   investigation/cases, time/utcStamp, admin/needsYou/needsYouApi, admin/needsYou/openings, ingest/studio/datasets,
//   ingest/studio/packs, ingest/runs/externalOrchestrationApi
//                             the cases client (the types, the pack list, the labels and the requests: list, create,
//                             rename, remove on the server, the datasets a case reads), the moment's words it uses, the
//                             reader's *Needs you* read and the request that waits for the place that takes it, the Studio's
//                             dataset and pack helpers, and the Runs tab's four requests for external orchestration (PL4
//                             slice D3d). Two files were split: the cases client's page half (`openCase`, `openCaseView`
//                             and forgetting a removed case in the tab) stays in the workspace as
//                             `investigation/caseNavigation.ts`, and the openings keep where a request is held in a storage
//                             handed in by `bindOpeningsStorage` (the workspace binds the tab's). One name was written
//                             twice, so the index gives it apart: the case's address `caseUrl` is `caseOpenUrl` (the report
//                             clients keep `caseUrl`)
//   canvas/nodeGestures, forceLayout, removeNodes, edgeSelection, settledAnchor, nodeDrag, nodeHitArea,
//   chunkedTextureRefresh, provenancePatterns, singleFlight, focusAnnouncement, linkLabel, zoomBands, edgeTypeMenu,
//   expansionGate, expansionPreview, expansionOutcome, layoutModes, cameraMoves, communityLinks, linkHover,
//   linksAmong, valueIcons; color/nodeVisual; ontology/schema
//                             the canvas's and the graph's plain logic (the gestures, the force and arranged layouts,
//                             the zoom bands, the link words, the expansion's gate and preview, the camera's redraws,
//                             the community links, the value icons), the node's drawing as one generated image, and the
//                             ontology's registry and its one request (PL4 slice E: twenty-five whole files, nothing
//                             split, nothing else changed). A Sigma, a graph or a scheduler is a parameter, never an
//                             import; the files that stay in the workspace's `canvas/` are the community files, the two
//                             that keep a choice in the browser, the five that need splitting and the three that import
//                             a drawing library
//
// What it must never import, as a value or as a type (I1, I13):
//   react, react-dom, react/jsx-runtime        no React, so `pages` can use it (ADR-152 decision 1)
//   zustand (the main entry), zustand/react    they import React: only `zustand/vanilla` is named here
//   sigma, @sigma/*, maplibre-gl               the drawing libraries are bound by each front end's own modules
// Two checks hold that: `scripts/no_react_check.mjs` and `scripts/version_isolation_check.mjs` (what a bundle
// reaches) and the `no-restricted-imports` block for this folder in `eslint.config.js` (what a source file
// names, a type import included: a bundler drops a type-only import, so only the lint rule sees it).
// `package.json` declares `sideEffects: false`: the registry registers itself at import, which a bundler would keep
// in every bundle that imports the package for one function (`src/manifest.test.ts` holds the flag).
export * from "./keyboard/actionRegistry";
export * from "./workingset/store";
export * from "./workingset/models";
export * from "./color/textContrast";
export * from "./map/contrast";
export * from "./map/conduitRequest";
export * from "./theme/theme";
export * from "./brand/brand";
export * from "./welcome/statement";
export * from "./color/tokens";
export * from "./color/palette";
export * from "./color/oklab";
export * from "./color/nodeGlyphs";
export * from "./layout/panelOrder";
export * from "./layout/layoutSizes";
export * from "./layout/sidePanelState";
export * from "./layout/panelFrameStore";
export * from "./layout/panelFrameAttach";
export * from "./admin/inviter";
export * from "./ingest/api";
export * from "./ingest/sources/api";
export * from "./ingest/releases/releasesApi";
export * from "./admin/sections/MapsApi";
export * from "./admin/sections/ModelsApi";
export * from "./admin/updateNotice";
export * from "./export/withheldSentence";
export * from "./export/api";
export * from "./models/modelDeadline";
export * from "./alerts/names";
export * from "./alerts/closingReasons";
export * from "./alerts/api";
export * from "./patterns/api";
export * from "./reports/api";
export * from "./reports/caseHttp";
export * from "./reports/dashboards";
export * from "./reports/trendsApi";
export * from "./reports/packText";
export * from "./reports/packsApi";
export * from "./dossier/models";
export * from "./dossier/api";
export * from "./inspector/emailDocuments";
export * from "./inspector/linkChangeApi";
export * from "./inspector/linkEventsApi";
export * from "./inspector/linkNotesApi";
export { LinkTypeError, type LinkTypeErrorKind, send as sendLinkType } from "./linktypes/http";
export * from "./linktypes/linkTypesApi";
export * from "./linktypes/modelProposalsApi";
export * from "./questions/graphFacts";
export {
  type AskScope,
  type Citation,
  type QuestionAnswer,
  type ReadFrom,
  type ReadSummary,
  type UnusableEngine,
  type WillRead,
  type WillReadScope,
  acceptProposal,
  askQuestion,
  listQuestions,
  rejectProposal as rejectQuestionProposal,
  willRead,
} from "./questions/questionsApi";
export * from "./reader/readerApi";
export * from "./views/viewsApi";
export * from "./workingset/batchExpansionApi";
export {
  type Answer,
  type LayerDeleted,
  type LayerDryRun,
  type LayerMergeSheet,
  type Promotion,
  type PromotionDetails,
  type PromotionSheet,
  type Promotions,
  type RemovedCaseLayers,
  type SheetItem,
  STATUS_WORDS,
  addsInWords,
  answered,
  boardPromotions,
  promote,
  promotionSheet,
  send as sendPromotion,
  startingTicks,
} from "./boards/promotionsApi";
export * from "./analytics/api";
export {
  getYardstick,
  listAssumptions,
  listGaps,
  listJudgements as listAssessmentJudgements,
  saveAssumption,
  type SaveAssumptionRequest,
  saveGap,
  type SaveGapRequest,
  saveJudgement,
  type SaveJudgementRequest,
  UnverifiableCitationApiError,
  type Yardstick,
  type YardstickBand,
} from "./assessment/api";
export {
  type Answer as BoardAnswer,
  type Asserted,
  type Board,
  type BoardOpened,
  boardPictures,
  type BoardPictures,
  choosePicture,
  decideMatch,
  declareItem,
  drawLink,
  type DrawnItemMade,
  type DrawnWatch,
  drawnWatches,
  editItem,
  type Grading,
  type ItemToDraw,
  type LinkToDraw,
  listBoards,
  makeBoard,
  matchSuggestions,
  type MatchSuggestions,
  moveItems,
  type NewDrawing,
  openBoard,
  pictureUrl,
  shareBoard,
  startDrawing,
  uploadPicture,
  withdrawItem,
  type Withdrawn,
} from "./boards/boardsApi";
export * from "./connections/connectionsApi";
export * from "./explore/exploreApi";
export * from "./map/providers";
export * from "./metrics/api";
export * from "./ownership/api";
export * from "./search/addFromListApi";
export * from "./site/api";
export * from "./site/bilinear";
export * from "./strength/api";
export * from "./watches/api";
export * from "./time/utcStamp";
export {
  type AccessLevel,
  caseDatasets,
  type CaseData,
  caseIsOpenable,
  caseLabel,
  type CaseListing,
  caseUrl as caseOpenUrl,
  createCase,
  type Dataset,
  datasetChoiceLabel,
  datasetLabel,
  DOMAIN_PACKS,
  domainLabels,
  type DomainPack,
  listCases,
  listDatasets,
  orderCases,
  POLE_LABEL,
  removeCaseOnServer,
  renameCase,
  scopeBadge,
  setCaseDatasets,
  sortedDomains,
  UNTITLED_CASE,
} from "./investigation/cases";
export * from "./admin/needsYou/needsYouApi";
export * from "./admin/needsYou/openings";
export * from "./ingest/studio/datasets";
export * from "./ingest/studio/packs";
export * from "./ingest/runs/externalOrchestrationApi";
export * from "./help/roles";
export { default as PLACES_BY_ROLE } from "./shell/placesByRole.json" with { type: "json" };
export {
  addPersonByObjectId,
  type AdminApi,
  type AuditQuery,
  authorAlsoNeeds,
  changeDatasetOwners,
  changeRole,
  changeSchedule,
  createRole,
  dashboardsSignInKind,
  datasetAuthors,
  datasetCases,
  datasetOwnerSetting,
  deleteRemovedLayer,
  disablePerson,
  disablePlan,
  enablePerson,
  guestSignIn,
  invitePerson,
  layerDryRun,
  linkOrganisation,
  listArrivals,
  listDashboards,
  listDatasets as listAdminDatasets,
  listDemoPacks,
  listPeople,
  listRoles,
  listSchedules,
  makeTeam,
  nameAnAuthor,
  operationsAgeing,
  pauseSchedule,
  peopleRows,
  personOwnership,
  readAudit,
  registerDashboard,
  removeDashboard,
  removePerson,
  resetSignIn,
  resumeSchedule,
  roleVersions,
  runScheduleNow,
  scheduleRuns,
  setAccess,
  setDatasetEgress,
  setDatasetOwnerSetting,
  setGuestSignIn,
  setPromotionAlertDays,
  setPromotionPolicy,
  setRoles,
  setTeamCover,
  setTeamLead,
  signInKind,
  systemStatus,
  testConnection as testAdminConnection,
  transferAndDisable,
} from "./admin/api";
export * from "./home/guides";
export * from "./home/homeData";
export * from "./reports/ruleGroup";
export * from "./canvas/entityPictures";
export * from "./canvas/nodeGestures";
export * from "./canvas/forceLayout";
export * from "./canvas/removeNodes";
export * from "./canvas/edgeSelection";
export * from "./canvas/settledAnchor";
export * from "./canvas/nodeDrag";
export * from "./canvas/nodeHitArea";
export * from "./canvas/chunkedTextureRefresh";
export * from "./canvas/provenancePatterns";
export * from "./canvas/singleFlight";
export * from "./canvas/focusAnnouncement";
export * from "./canvas/linkLabel";
export * from "./canvas/zoomBands";
export * from "./canvas/edgeTypeMenu";
export * from "./canvas/expansionGate";
export * from "./canvas/expansionPreview";
export * from "./canvas/expansionOutcome";
export * from "./canvas/layoutModes";
export * from "./canvas/cameraMoves";
export * from "./canvas/communityLinks";
export * from "./canvas/linkHover";
export * from "./canvas/linksAmong";
export * from "./canvas/valueIcons";
export * from "./color/nodeVisual";
export * from "./ontology/schema";
