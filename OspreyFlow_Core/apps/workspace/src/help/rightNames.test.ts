// L1.8: a right's name on screen, and who can, from `roles.ts`. What would fail if each were wrong:
// - a right's name saying "target model" where the screens say "domain model" (ADR-140 Amendment 9
//   decision 1), as `edit_target_model` did — `every right's name says what the screens say`;
// - Admin › Roles building a right's name its own way, so "Edit target model" stays on screen there —
//   `Admin's right names are these` (red until rules-b's `admin-tips.patch`, which makes Admin's
//   `rightWords` this `rightName`; the lane review of L1.8);
// - who-can naming a role id, a person, the Super user preset or a role that does not hold the right —
//   `who can is the built-in roles that hold the right, by name`, read from `placesByRole.json`, the
//   record `test_place_routes.py` holds to the routes.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { rightWords } from "../admin/sections/Roles";
import BY_ROLE from "../shell/placesByRole.json";
import { rightName, rolesHolding, ROLE_WORDS, whyNotByRole, type Right } from "./roles";

const RIGHTS_PY = join(dirname(fileURLToPath(import.meta.url)), "../../../../packages/schemas/rights.py");
const DECLARED = (() => {
  const source = readFileSync(RIGHTS_PY, "utf8");
  const body = source.slice(source.indexOf("class Right(StrEnum):"), source.indexOf("\nR = Right"));
  return [...body.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]!) as Right[];
})();
const RECORDED = (BY_ROLE as { roles: Record<string, { rights?: string[] }> }).roles;

describe("a right's name and who can", () => {
  it("every right's name says what the screens say", () => {
    expect(DECLARED).toContain("edit_target_model");
    expect(DECLARED.filter((r) => /target\s+model/i.test(rightName(r)))).toEqual([]);
    expect(rightName("edit_target_model")).toBe("Edit domain model");
    expect(rightName("review_promotions")).toBe("Review promotions");
  });

  it("Admin's right names are these", () => {
    for (const right of DECLARED) expect(rightWords(right)).toBe(rightName(right));
  });

  it("who can is the built-in roles that hold the right, by name", () => {
    for (const right of DECLARED) {
      const holders = Object.entries(RECORDED)
        .filter(([key, role]) => key !== "super" && ROLE_WORDS[key] !== undefined && role.rights?.includes(right))
        .map(([key]) => ROLE_WORDS[key]!.name);
      expect(rolesHolding(right).slice().sort()).toEqual(holders.slice().sort());
      const words = whyNotByRole(right);
      expect(words.startsWith(`You need ${rightName(right)}; `)).toBe(true);
      expect(words).not.toMatch(/_|Super user|target model/i);
      // A name, never an id: every role named is one the words name.
      const names = new Set(Object.values(ROLE_WORDS).map((r) => r.name));
      for (const role of rolesHolding(right)) expect(names.has(role)).toBe(true);
    }
  });

  it("says one role, several roles, and none, in plain words", () => {
    expect(whyNotByRole("review_promotions")).toBe(
      "You need Review promotions; the Data Engineer role has it. Ask an administrator to give it to you.",
    );
    expect(whyNotByRole("edit_pipelines")).toBe(
      "You need Edit pipelines; the Data Engineer role has it. Ask an administrator to give it to you.",
    );
    expect(whyNotByRole("revert_loads")).toBe(
      "You need Revert loads; the Administrator and Data Engineer roles have it. Ask an administrator to give you one.",
    );
    const nobody = DECLARED.find((r) => rolesHolding(r).length === 0);
    if (nobody) expect(whyNotByRole(nobody)).toBe(`You need ${rightName(nobody)}; no built-in role has it. Ask an administrator.`);
  });
});
