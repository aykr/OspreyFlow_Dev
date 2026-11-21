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
//   layout/layoutSizes, panelOrder, sidePanelState
//                             the sizes, the panel order and the side panel's mode, kept in this browser: the plain
//                             halves (the React hooks over them stay in the workspace's files of the same names)
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
