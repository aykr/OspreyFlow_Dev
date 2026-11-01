// ADR-133 stage (c): the four new AML templates in the rule form. Each is typed parameters (rule 8):
// a jurisdiction list as two-letter codes the Author enters, cash types, a measure; the two that read
// an account's stored past run after commit whatever the form says; each rule reads back in words.
import { describe, expect, it } from "vitest";

import type { TypologyRule } from "../../../../packages/schemas/generated";
import { AFTER_COMMIT_ONLY, describeParams, jurisdictionCodes, PARAMETERS, ruleInput } from "./RulesPanel";
import { TEMPLATES } from "./templates";

function rule(params: Record<string, unknown>): TypologyRule {
  return { id: "r", investigation_id: "c", owner_id: "o", name: "n", created_at: "", params, trigger: "post_commit" } as unknown as TypologyRule;
}

describe("the AML templates", () => {
  it("are offered as templates for AML transaction monitoring", () => {
    const aml = TEMPLATES.filter((t) => t.group === "AML transaction monitoring").map((t) => t.typology);
    expect(aml).toEqual(["structuring", "rapid_movement", "circular_flow", "high_risk_jurisdiction", "large_cash", "dormant_reactivated", "velocity_rise"]);
  });

  it("send a jurisdiction list as codes, upper-cased, once each", () => {
    expect(jurisdictionCodes("xa, XB;xa  xc")).toEqual(["XA", "XB", "XC"]);
    const input = ruleInput("Risky places", "high_risk_jurisdiction", {}, "pre_commit", 5000, {}, undefined, "", {
      jurisdictions: jurisdictionCodes("xa xb"),
    });
    expect(input).toEqual({ name: "Risky places", params: { typology: "high_risk_jurisdiction", jurisdictions: ["XA", "XB"] }, trigger: "pre_commit", budget_ms: 5000 });
  });

  it("send large cash with its threshold and cash types", () => {
    const input = ruleInput("Cash", "large_cash", { threshold: "15000" }, "post_commit", 5000, {}, undefined, "", { cashTypes: ["CASH_IN"] });
    expect(input.params).toEqual({ typology: "large_cash", threshold: 15000, cash_types: ["CASH_IN"] });
    expect(ruleInput("Cash", "large_cash", {}, "post_commit", 5000).params).toEqual({ typology: "large_cash", threshold: 10000, cash_types: ["CASH_IN", "CASH_OUT"] });
  });

  it("run an account against its own past after commit, whatever the form was set to", () => {
    for (const typology of ["dormant_reactivated", "velocity_rise"] as const) {
      expect(AFTER_COMMIT_ONLY.has(typology)).toBe(true);
      expect(ruleInput("Past", typology, {}, "pre_commit", 5000).trigger).toBe("post_commit");
    }
    expect(ruleInput("Rise", "velocity_rise", {}, "post_commit", 5000, {}, undefined, "", { measure: "amount" }).params).toEqual({
      typology: "velocity_rise", recent_days: 7, baseline_days: 90, factor: 3, min_recent: 5, measure: "amount",
    }); // prettier-ignore
    expect(PARAMETERS.dormant_reactivated.map((f) => [f.key, f.fallback])).toEqual([["dormant_days", 180]]);
  });

  it("read back in words", () => {
    expect(describeParams(rule({ typology: "high_risk_jurisdiction", jurisdictions: ["XA", "XB"] }))).toBe(
      "a payment to or from an account held in XA, XB (its IBAN country code)",
    );
    expect(describeParams(rule({ typology: "large_cash", threshold: 10000, cash_types: ["CASH_IN", "CASH_OUT"] }))).toBe(
      "cash paid in or drawn out of 10,000 or more in one movement",
    );
    expect(describeParams(rule({ typology: "dormant_reactivated", dormant_days: 180 }))).toContain("after 180 days or more without a movement");
    expect(describeParams(rule({ typology: "velocity_rise", recent_days: 7, baseline_days: 90, factor: 3, min_recent: 5, measure: "count" }))).toBe(
      "an account's movements over the last 7 day(s) at 3 times or more its own daily rate over the 90 days before, with 5 or more movements; runs after each load commits",
    );
  });
});
