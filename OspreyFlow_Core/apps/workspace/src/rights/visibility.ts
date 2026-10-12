// ADR-112: what the Glass offers, from the person's rights (`GET /v1/me/rights`). A convenience,
// never the gate — every route checks its own right — so the Glass leaves out what it would only
// be refused. While the rights are unknown (`null`) it shows what it always showed, except the
// Admin area, which appears only once an administration right is known.

export type Rights = ReadonlySet<string> | null;
export type RailEntry =
  | "cases" | "watches" | "alerts" | "ownership" | "history" | "explore" | "questions" | "types" | "ingest" | "dashboards" | "admin";
export type GlassView = "graph" | "map" | "reports";

const has = (rights: Rights, ...any: string[]) => rights === null || any.some((r) => rights.has(r));
const known = (rights: Rights, ...any: string[]) => rights !== null && any.some((r) => rights.has(r));

/** Any one of these opens the Admin area. */
const ADMINISTRATION = ["manage_people", "manage_dashboards", "administer_system", "operate_schedules"];

export function railEntries(rights: Rights): RailEntry[] {
  const entries: [RailEntry, boolean][] = [
    ["cases", true],
    ["watches", has(rights, "keep_watches")],
    ["alerts", has(rights, "read_alert_queue")],
    ["ownership", has(rights, "trace_ownership")],
    ["history", has(rights, "investigate")],
    ["explore", has(rights, "investigate")],
    ["questions", has(rights, "ask_model")],
    ["types", known(rights, "manage_ontology")],
    // The Studio is for pipelines; an analyst adds files from the canvas's *Add files* (the
    // launcher's Ingest Studio tile follows the same rule).
    ["ingest", has(rights, "edit_pipelines")],
    // ADR-111 Amendment 3: the Superset boards this person may open, drawn inside the Glass.
    ["dashboards", known(rights, "read_reports")],
    ["admin", known(rights, ...ADMINISTRATION)],
  ];
  return entries.filter(([, shown]) => shown).map(([entry]) => entry);
}

// ADR-114 Amendment 5 point 9: Start — where a person may go after signing in, with no case open.
export type StartPlace = "glass" | "ingest" | "admin";

export function startPlaces(rights: Rights): StartPlace[] {
  const places: [StartPlace, boolean][] = [
    ["glass", has(rights, "investigate", "read_reports")],
    ["ingest", has(rights, "edit_pipelines")],
    ["admin", known(rights, ...ADMINISTRATION)],
  ];
  return places.filter(([, shown]) => shown).map(([place]) => place);
}

/** Start itself, or the place to go: the one chosen, else a person's only place. */
export function startFor(places: readonly StartPlace[], chosen: StartPlace | "start" | null): StartPlace | "start" {
  if (chosen) return chosen;
  return places.length === 1 && places[0] ? places[0] : "start";
}

export function viewsFor(rights: Rights): GlassView[] {
  const views: [GlassView, boolean][] = [
    ["graph", has(rights, "investigate")],
    ["map", has(rights, "investigate")],
    ["reports", has(rights, "read_reports")],
  ];
  return views.filter(([, shown]) => shown).map(([view]) => view);
}

/** Where a person lands: the graph if they investigate, else the first view they may open. */
export function landingView(rights: Rights): GlassView {
  return viewsFor(rights)[0] ?? "graph";
}

/** The Inspector and its judgements are investigation tools: a Reports Viewer, who may not
 * investigate, is not offered a panel whose every action they would be refused. */
export function showsInspector(rights: Rights): boolean {
  return has(rights, "investigate");
}

export function canDownloadFeed(rights: Rights): boolean {
  return known(rights, "read_report_feed");
}

// ADR-113: the Reports place's tabs. Each is a convenience over a route that checks its own right.
/** Trends are built from the case's events: the right to run analysis. */
export function canBuildTrends(rights: Rights): boolean {
  return has(rights, "run_analysis");
}

/** Packs are assembled from assessments and trends: the right to record an assessment. */
export function canAssemblePacks(rights: Rights): boolean {
  return has(rights, "record_assessment");
}

/** Published packs are what a Reports Viewer reads. */
export function canReadPublished(rights: Rights): boolean {
  return has(rights, "read_reports");
}

/** A pack leaves the platform only through the export right. */
export function canExportPacks(rights: Rights): boolean {
  return has(rights, "export");
}
