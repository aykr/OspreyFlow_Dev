// One set of words for roles, teams and Authors (ADR-145 Amendment 4 decision 12): every right in
// `packages/schemas/rights.py` is said in `roles.ts`, the help page draws them all from there, and an
// action a person cannot take says why and who can.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import BY_ROLE from "../shell/placesByRole.json";
import { RIGHT_WORDS, ROLE_WORDS, rightSays, whyNot } from "./roles";

const RIGHTS_PY = join(dirname(fileURLToPath(import.meta.url)), "../../../../packages/schemas/rights.py");

/** The rights `rights.py` declares, read from its `Right` enum. */
function declaredRights(source = readFileSync(RIGHTS_PY, "utf8")): string[] {
  const body = source.slice(source.indexOf("class Right(StrEnum):"), source.indexOf("\nR = Right"));
  return [...body.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]!);
}

describe("the words for roles, teams and Authors", () => {
  it("say only rights rights.py declares, read from it at test time", () => {
    const declared = declaredRights();
    expect(declared).toContain("create_case");
    expect(Object.keys(RIGHT_WORDS).filter((r) => !declared.includes(r))).toEqual([]);
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

  it("say why an action cannot be taken and who can, never only that it cannot", () => {
    expect(whyNot("review_promotions", ["D. Engineer", "S. Lead"])).toBe("You need Review promotions; D. Engineer and S. Lead have it.");
    expect(whyNot("review_promotions", ["D. Engineer"])).toBe("You need Review promotions; D. Engineer has it.");
    expect(whyNot("merge_datasets", [])).toBe("You need Merge datasets; no one you can see has it. Ask an administrator.");
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
