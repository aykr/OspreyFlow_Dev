// One set of words for roles, teams and Authors (ADR-145 Amendment 4 decision 12): every right in
// `packages/schemas/rights.py` is said in `roles.ts`, the help page draws them all from there, and an
// action a person cannot take says why and who can.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import BY_ROLE from "../shell/placesByRole.json";
import { RIGHT_WORDS, ROLE_WORDS, whyNot } from "./roles";

const RIGHTS_PY = join(dirname(fileURLToPath(import.meta.url)), "../../../../packages/schemas/rights.py");

/** The rights `rights.py` declares, read from its `Right` enum. */
function declaredRights(source = readFileSync(RIGHTS_PY, "utf8")): string[] {
  const body = source.slice(source.indexOf("class Right(StrEnum):"), source.indexOf("\nR = Right"));
  return [...body.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]!);
}

describe("the words for roles, teams and Authors", () => {
  it("say every right rights.py declares, and no other", () => {
    const declared = declaredRights();
    expect(declared.length).toBeGreaterThan(40);
    expect(Object.keys(RIGHT_WORDS).sort()).toEqual([...declared].sort());
  });

  it("are found missing when rights.py declares a right they do not say", () => {
    const planted = readFileSync(RIGHTS_PY, "utf8").replace(
      '    MANAGE_MODELS = "manage_models"',
      '    MANAGE_MODELS = "manage_models"\n    APPROVE_RELEASES = "approve_releases"',
    );
    const missing = declaredRights(planted).filter((r) => !(r in RIGHT_WORDS));
    expect(missing).toEqual(["approve_releases"]);
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
