// ADR-112: the Glass leaves out what a person would only be refused — the Conduit still refuses it.
// Each role's view of the rail and the view switch, from the rights `GET /v1/me/rights` returns.
import { describe, expect, it } from "vitest";

import {
  canAssemblePacks,
  canBuildTrends,
  canDownloadFeed,
  canExportPacks,
  canReadPublished,
  landingView,
  railEntries,
  showsInspector,
  homePanels,
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
    expect(railEntries(new Set(ANALYST))).toEqual(["cases", "watches", "alerts", "ownership", "history", "explore", "questions", "dashboards"]);
    expect(viewsFor(new Set(ANALYST))).toEqual(["graph", "map", "reports"]);
    expect(landingView(new Set(ANALYST))).toBe("graph");
  });

  it("offers a data engineer the Studio and no watches or ownership", () => {
    expect(railEntries(new Set(ENGINEER))).toEqual(["cases", "alerts", "history", "explore", "ingest", "dashboards"]);
  });

  it("offers an administrator the Admin area and nothing of a case's content", () => {
    expect(railEntries(new Set(ADMIN))).toEqual(["cases", "types", "admin"]);
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
    expect(railEntries(null)).toContain("ingest");
    expect(railEntries(null)).not.toContain("admin");
    expect(railEntries(null)).not.toContain("dashboards"); // ADR-111 Am. 3: only once the right is known
    expect(viewsFor(null)).toEqual(["graph", "map", "reports"]);
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
    expect(startPlaces(new Set(ANALYST))).toEqual(["glass"]);
    expect(startPlaces(new Set(ENGINEER))).toEqual(["glass", "ingest"]);
    expect(startPlaces(new Set(ADMIN))).toEqual(["admin"]);
    expect(startPlaces(new Set([...ENGINEER, ...ADMIN]))).toEqual(["glass", "ingest", "admin"]);
    expect(startPlaces(new Set(READER))).toEqual(["glass"]);
    expect(startPlaces(null)).toEqual(["glass", "ingest"]);
  });

  it("lands everyone on Home, a person with one place too, and goes to the place they chose", () => {
    expect(startFor(null)).toBe("start");
    expect(startFor("admin")).toBe("admin");
    expect(startFor("start")).toBe("start");
  });

  it("gives Home all three panels, each usable or naming the role that opens it", () => {
    expect(homePanels(new Set(READER))).toEqual([
      { place: "glass", allowed: true, role: "Analyst" },
      { place: "ingest", allowed: false, role: "Data Engineer" },
      { place: "admin", allowed: false, role: "Admin" },
    ]);
  });
});
