// ADR-112: what the Glass offers, from the person's rights (`GET /v1/me/rights`). A convenience,
// never the gate — every route checks its own right — so the Glass leaves out what it would only
// be refused. While the rights are unknown (`null`) it shows what it always showed, except the
// Admin area, which appears only once an administration right is known.
import { placesFor, type PlaceId } from "../shell/places";

export type Rights = ReadonlySet<string> | null;
// ADR-145 decision 1: the Ingest Studio, Admin and Proposed types left the rail for the place
// switcher (`shell/places.ts`); proposed types are decided on the Studio's Model tab since L2.7.
// ADR-146 decision 2: Monitoring left the Glass for Rules and Monitoring, a place of its own; its
// Connection strength (ADR-139), which is not alerts, stayed in the Glass under the rail's More.
export type RailEntry = "cases" | "ownership" | "history" | "explore" | "questions" | "dashboards" | "strength";
export type GlassView = "graph" | "map" | "matrix" | "reports";

const has = (rights: Rights, ...any: string[]) => rights === null || any.some((r) => rights.has(r));
const known = (rights: Rights, ...any: string[]) => rights !== null && any.some((r) => rights.has(r));

export function railEntries(rights: Rights): RailEntry[] {
  const entries: [RailEntry, boolean][] = [
    ["cases", true],
    ["ownership", has(rights, "trace_ownership")],
    ["history", has(rights, "investigate")],
    ["explore", has(rights, "investigate")],
    ["questions", has(rights, "ask_model")],
    // ADR-111 Amendment 3: the Superset boards this person may open, drawn inside the Glass.
    ["dashboards", known(rights, "read_reports")],
    // ADR-139: what makes a link strong in this case (`investigate`), and the installation-wide
    // influencers (`manage_strength_influencers`).
    ["strength", has(rights, "investigate", "manage_strength_influencers")],
  ];
  return entries.filter(([, shown]) => shown).map(([entry]) => entry);
}

// ADR-114 Amendment 5 point 9: Start — where a person may go after signing in, with no case open.
// ADR-145 N6: the places their rights open, the switcher's list and Home's cards alike.
export type StartPlace = PlaceId;

export function startPlaces(rights: Rights): StartPlace[] {
  return placesFor(rights);
}

/** Home itself, or the place chosen on it. ADR-115 decision 7: every signed-in person lands on Home
 * with no case open. ADR-115 Amendment 6 (ADR-145 N6): Home shows only the places the person's rights
 * open; one they cannot open is hidden, not dimmed. */
export function startFor(chosen: StartPlace | "start" | null): StartPlace | "start" {
  return chosen ?? "start";
}


export function viewsFor(rights: Rights): GlassView[] {
  const views: [GlassView, boolean][] = [
    ["graph", has(rights, "investigate")],
    ["map", has(rights, "investigate")],
    // `02_GLASS_FRONTEND.md` §6: the screen-reader-navigable rendering of the same working set.
    ["matrix", has(rights, "investigate")],
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

/** A case's own settings, "Data this case reads" and "Domain models" (ADR-099, ADR-126), are offered
 * to the case's Author who also holds `share_case`: the level and the right are both asked of the
 * Conduit (`PUT .../datasets`, `PATCH /investigations/{id}`), so the Glass offers only what both
 * would allow. While the rights are unknown an Author is offered them, as the rest of this file
 * does. */
export function canChangeCase(rights: Rights, level: string | undefined): boolean {
  return level === "author" && has(rights, "share_case");
}

/** Packs are assembled from assessments and trends: the right to record an assessment. */
export function canAssemblePacks(rights: Rights): boolean {
  return has(rights, "record_assessment");
}

/** Published packs are what a Reports Viewer reads. */
/** ADR-110 decision 9: the Reports view's Data feeds tab. */
export function canReadDataFeeds(rights: Rights): boolean {
  return has(rights, "read_data_feeds");
}

export function canReadPublished(rights: Rights): boolean {
  return has(rights, "read_reports");
}

/** A pack leaves the platform only through the export right. */
export function canExportPacks(rights: Rights): boolean {
  return has(rights, "export");
}

/** ADR-146 decision 4: *Watch for this* and *Save as a watch*, made in the Glass and kept in Rules
 * and Monitoring, whose gate the routes ask for: offered to whom the place is offered and who keeps
 * watches. */
export function canKeepWatches(rights: Rights): boolean {
  return has(rights, "keep_watches") && (rights === null || placesFor(rights).includes("rules"));
}

/** ADR-146 decision 7: *Raise an alert…*, a Glass action of whoever investigates the case. */
export function canRaiseAlerts(rights: Rights): boolean {
  return has(rights, "investigate");
}
