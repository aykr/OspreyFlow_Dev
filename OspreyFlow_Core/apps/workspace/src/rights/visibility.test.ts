// ADR-112: the Glass leaves out what a person would only be refused — the Conduit still refuses it.
// Each role's view of the rail and the view switch, from the rights `GET /v1/me/rights` returns.
import { describe, expect, it } from "vitest";

import { canDownloadFeed, landingView, railEntries, viewsFor } from "./visibility";

const ANALYST = ["investigate", "keep_watches", "read_alert_queue", "trace_ownership", "ask_model", "read_reports", "add_ingest_files"];
const ENGINEER = ["investigate", "read_alert_queue", "edit_pipelines", "read_reports"];
const ADMIN = ["manage_people", "manage_dashboards", "administer_system", "manage_ontology"];
const READER = ["read_alert_queue", "read_reports", "read_report_feed", "read_data_feeds"];

describe("what the Glass offers each role", () => {
  it("offers an analyst the investigation and no administration", () => {
    expect(railEntries(new Set(ANALYST))).toEqual(["cases", "watches", "alerts", "ownership", "history", "explore", "questions"]);
    expect(viewsFor(new Set(ANALYST))).toEqual(["graph", "map", "reports"]);
    expect(landingView(new Set(ANALYST))).toBe("graph");
  });

  it("offers a data engineer the Studio and no watches or ownership", () => {
    expect(railEntries(new Set(ENGINEER))).toEqual(["cases", "alerts", "history", "explore", "ingest"]);
  });

  it("offers an administrator the Admin area and nothing of a case's content", () => {
    expect(railEntries(new Set(ADMIN))).toEqual(["cases", "types", "admin"]);
    expect(viewsFor(new Set(ADMIN))).toEqual([]);
  });

  it("lands a reports viewer on Reports, with the alerts and the feed", () => {
    expect(railEntries(new Set(READER))).toEqual(["cases", "alerts"]);
    expect(viewsFor(new Set(READER))).toEqual(["reports"]);
    expect(landingView(new Set(READER))).toBe("reports");
    expect(canDownloadFeed(new Set(READER))).toBe(true);
    expect(canDownloadFeed(new Set(ANALYST))).toBe(false);
  });

  it("shows what it always showed while the rights are not yet known", () => {
    expect(railEntries(null)).toContain("ingest");
    expect(railEntries(null)).not.toContain("admin");
    expect(viewsFor(null)).toEqual(["graph", "map", "reports"]);
  });
});
