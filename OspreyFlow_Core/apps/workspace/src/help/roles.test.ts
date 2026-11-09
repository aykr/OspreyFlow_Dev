// One set of words for roles, teams and Authors (ADR-145 Amendment 4 decision 12): every right in
// `packages/schemas/rights.py` is said in `roles.ts`, the help page draws them all from there, and an
// action a person cannot take says why and who can.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import BY_ROLE from "../shell/placesByRole.json";
import * as ROLES_MODULE from "./roles";
import { RIGHT_WORDS, ROLE_WORDS, rightSays } from "./roles";

const RIGHTS_PY = join(dirname(fileURLToPath(import.meta.url)), "../../../../packages/schemas/rights.py");

/** The rights `rights.py` declares, read from its `Right` enum. */
function declaredRights(source = readFileSync(RIGHTS_PY, "utf8")): string[] {
  const body = source.slice(source.indexOf("class Right(StrEnum):"), source.indexOf("\nR = Right"));
  return [...body.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]!);
}

/** The rights worded when L2.12 was built: each keeps its own words (deleting one is red), whatever
 * another lane adds to `rights.py` after (said by its name until worded, not red). */
const WORDED = [
  "create_case", "share_case", "remove_case", "export", "export_override", "investigate", "edit_graph",
  "confirm_inferred", "extract_files", "resolve_entities", "record_assessment", "ask_model", "run_analysis",
  "propose_link_type", "draw_on_boards", "promote_to_dataset", "propose_types", "read_alert_queue",
  "triage_alerts", "deploy_rules", "read_rule_audit", "read_held_rows", "decide_held_rows",
  "trace_ownership", "keep_watches", "load_screening_lists", "author_rules", "manage_strength_influencers",
  "edit_pipelines", "verify_pipelines", "publish_pipelines", "run_pipelines", "schedule_pipelines",
  "add_ingest_files", "revert_loads", "edit_target_model", "review_promotions", "accept_types",
  "merge_datasets", "read_reports", "read_report_feed", "read_data_feeds", "administer_system",
  "manage_people", "manage_dashboards", "operate_schedules", "manage_ontology", "manage_geospatial",
  "read_audit", "read_export_ledger", "manage_models",
];

describe("the words for roles, teams and Authors", () => {
  it("say only rights rights.py declares, read from it at test time", () => {
    const declared = declaredRights();
    expect(declared).toContain("create_case");
    expect(Object.keys(RIGHT_WORDS).filter((r) => !declared.includes(r))).toEqual([]);
  });

  it("keep their own words for every right worded when they were written", () => {
    expect(WORDED).toHaveLength(51);
    expect(WORDED.filter((r) => !RIGHT_WORDS[r as keyof typeof RIGHT_WORDS])).toEqual([]);
    expect(WORDED.filter((r) => !declaredRights().includes(r))).toEqual([]);
  });

  it("stay green when another lane adds a right to rights.py, and say it by its name", () => {
    const source = readFileSync(RIGHTS_PY, "utf8");
    const planted = source.replace(/^(\s+CREATE_CASE = "create_case".*)$/m, '$1\n    RAISE_ALERTS = "raise_alerts"');
    expect(declaredRights(planted)).toContain("raise_alerts");
    expect(Object.keys(RIGHT_WORDS).filter((r) => !declaredRights(planted).includes(r))).toEqual([]);
    expect(rightSays("raise_alerts")).toBe("Raise alerts.");
    expect(rightSays("create_case")).toBe(RIGHT_WORDS.create_case);
  });

  it("are found stale when rights.py no longer declares a right they say", () => {
    const planted = readFileSync(RIGHTS_PY, "utf8").replace(/^\s+CREATE_CASE = "create_case".*\n/m, "");
    expect(Object.keys(RIGHT_WORDS).filter((r) => !declaredRights(planted).includes(r))).toEqual(["create_case"]);
  });

  it("name no person who holds a right: no refusal here takes people", () => {
    // The owner's ruling (c) on ADR-145 Amendment 4 decision 12: a refusal names the roles that hold the
    // right, never people (studio-b's `whyNotByRole`, L1.8). No export of these words takes holders.
    const takesPeople = Object.entries(ROLES_MODULE).filter(([, v]) => typeof v === "function" && /holders|people/.test(String(v)));
    expect(takesPeople.map(([k]) => k)).toEqual([]);
  });
});


describe("the roles' places", () => {
  it("are the record's, for every role said, and each opens at least the Glass", () => {
    const recorded = (BY_ROLE as { roles: Record<string, { places: string[] }> }).roles;
    for (const [key, role] of Object.entries(ROLE_WORDS)) {
      expect(recorded[key], `${key} is not in placesByRole.json`).toBeTruthy();
      expect(role.places).toEqual(recorded[key]!.places);
      expect(role.places).toContain("glass");
    }
    expect(ROLE_WORDS.data_engineer!.places).toEqual(["glass", "ingest", "admin"]);
  });
});
