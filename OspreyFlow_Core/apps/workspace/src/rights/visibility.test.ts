// ADR-112: the Glass leaves out what a person would only be refused — the Conduit still refuses it.
// Each role's view of the rail and the view switch, from the rights `GET /v1/me/rights` returns.
import { describe, expect, it } from "vitest";

import {
  canAssemblePacks,
  canChangeCase,
  canBuildTrends,
  canDownloadFeed,
  canExportPacks,
  canReadPublished,
  landingView,
  railEntries,
  showsInspector,
  startFor,
  startPlaces,
  viewsFor,
} from "./visibility";

const ANALYST = ["investigate", "keep_watches", "read_alert_queue", "trace_ownership", "ask_model", "read_reports", "add_ingest_files"];
const ENGINEER = ["investigate", "read_alert_queue", "edit_pipelines", "read_reports"];
const ADMIN = ["manage_people", "manage_dashboards", "administer_system", "manage_ontology"];
const READER = ["read_alert_queue", "read_reports", "read_report_feed", "read_data_feeds"];

describe("what the Glass offers each role", () => {
  it("offers an analyst the investigation and no administration", () => {
    // The owner's answer of 1 November 2026: no Watches entry; watches are in Monitoring's Watches tab.
    expect(railEntries(new Set(ANALYST))).toEqual(["cases", "alerts", "ownership", "history", "explore", "questions", "dashboards"]);
    expect(viewsFor(new Set(ANALYST))).toEqual(["graph", "map", "matrix", "reports"]);
    expect(landingView(new Set(ANALYST))).toBe("graph");
  });

  it("keeps watches reachable for someone who keeps watches but does not read the queue", () => {
    // With the rail's Watches entry gone, Monitoring is where watches are: a person granted
    // `keep_watches` alone must still be offered it, or their watches would be unreachable.
    expect(railEntries(new Set(["investigate", "keep_watches"]))).toContain("alerts");
    expect(railEntries(new Set(["investigate"]))).not.toContain("alerts");
  });

  it("offers a data engineer the Studio and no watches or ownership", () => {
    // ADR-145 decision 1: the Studio is a place of its own, reached from the switcher, not the rail.
    expect(railEntries(new Set(ENGINEER))).toEqual(["cases", "alerts", "history", "explore", "dashboards"]);
  });

  it("offers an administrator the Admin area and nothing of a case's content", () => {
    // ADR-145 decision 1: Admin and Proposed types left the rail (Proposed types is an Admin tab).
    expect(railEntries(new Set(ADMIN))).toEqual(["cases"]);
    expect(viewsFor(new Set(ADMIN))).toEqual([]);
  });

  it("lands a reports viewer on Reports, with the alerts and the feed", () => {
    expect(railEntries(new Set(READER))).toEqual(["cases", "alerts", "dashboards"]);
    expect(viewsFor(new Set(READER))).toEqual(["reports"]);
    expect(landingView(new Set(READER))).toBe("reports");
    expect(canDownloadFeed(new Set(READER))).toBe(true);
    expect(showsInspector(new Set(READER))).toBe(false);
    expect(showsInspector(new Set(ANALYST))).toBe(true);
    expect(canDownloadFeed(new Set(ANALYST))).toBe(false);
  });

  it("shows what it always showed while the rights are not yet known", () => {
    expect(railEntries(null)).toContain("history");
    expect(railEntries(null)).not.toContain("dashboards"); // ADR-111 Am. 3: only once the right is known
    expect(viewsFor(null)).toEqual(["graph", "map", "matrix", "reports"]);
  });
});

describe("what the Reports place offers each role (ADR-113)", () => {
  const FOUR = [canBuildTrends, canAssemblePacks, canReadPublished, canExportPacks];

  it("offers everything while the rights are not yet known", () => {
    for (const helper of FOUR) expect(helper(null)).toBe(true);
  });

  it("offers a reports viewer the published packs and nothing that builds or exports", () => {
    const rights = new Set(READER);
    expect(canReadPublished(rights)).toBe(true);
    expect(canBuildTrends(rights)).toBe(false);
    expect(canAssemblePacks(rights)).toBe(false);
    expect(canExportPacks(rights)).toBe(false);
  });

  it("asks each helper for its own right and no other", () => {
    expect(canBuildTrends(new Set(["run_analysis"]))).toBe(true);
    expect(canBuildTrends(new Set(["record_assessment", "export", "read_reports"]))).toBe(false);
    expect(canAssemblePacks(new Set(["record_assessment"]))).toBe(true);
    expect(canAssemblePacks(new Set(["run_analysis", "export", "read_reports"]))).toBe(false);
    expect(canExportPacks(new Set(["export"]))).toBe(true);
    expect(canExportPacks(new Set(["run_analysis", "record_assessment", "read_reports"]))).toBe(false);
  });
});

// ADR-114 Amendment 5 point 9: Start — the places a person may go after signing in, with no case open.
describe("Start", () => {
  it("offers each place the person's rights open, Admin only once an administration right is known", () => {
    // ADR-145 N6, from `shell/places.json` (the table `test_place_routes.py` checks the routes against).
    expect(startPlaces(new Set(ANALYST.filter((r) => r !== "add_ingest_files")))).toEqual(["glass"]);
    expect(startPlaces(new Set(ENGINEER))).toEqual(["glass", "ingest"]);
    expect(startPlaces(new Set([...ENGINEER, "operate_schedules"]))).toEqual(["glass", "ingest", "admin"]);
    expect(startPlaces(new Set(ADMIN))).toEqual(["admin"]);
    expect(startPlaces(new Set([...ADMIN, "share_case"]))).toEqual(["glass", "admin"]);
    expect(startPlaces(new Set(READER))).toEqual(["glass"]);
    // ADR-145 Amendment 1: `manage_ontology` alone opens nothing; its routes ask for the administrator role too.
    expect(startPlaces(new Set(["manage_ontology"]))).toEqual([]);
    expect(startPlaces(new Set())).toEqual([]);
    // ADR-145 N6: nothing is offered until the rights are known.
    expect(startPlaces(null)).toEqual([]);
  });

  it("lands everyone on Home, a person with one place too, and goes to the place they chose", () => {
    expect(startFor(null)).toBe("start");
    expect(startFor("admin")).toBe("admin");
    expect(startFor("start")).toBe("start");
  });

  it("offers a case's settings only to an Author who holds share_case (ADR-126, ADR-099)", () => {
    expect(canChangeCase(new Set(["share_case"]), "author")).toBe(true);
    expect(canChangeCase(new Set(["investigate"]), "author")).toBe(false);
    expect(canChangeCase(new Set(["share_case"]), "editor")).toBe(false);
    expect(canChangeCase(new Set(["share_case"]), undefined)).toBe(false);
    // Rights not yet known: what was always shown, for an Author; the Conduit still decides.
    expect(canChangeCase(null, "author")).toBe(true);
    expect(canChangeCase(null, "viewer")).toBe(false);
  });
});
