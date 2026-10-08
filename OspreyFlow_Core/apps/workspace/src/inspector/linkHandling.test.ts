// ADR-102: what counts as lowering a link's handling, mirrored from `ontology.handling.
// merge_handling` so the form can say so before the server refuses. The server still decides.
import { describe, expect, it } from "vitest";

import type { Handling } from "../../../../packages/schemas/generated";
import type { HandlingScheme } from "../ingest/api";
import { lowerParts } from "./linkHandling";

const SCHEME: HandlingScheme = {
  name: "uk-le",
  classification: ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"],
  handling_codes: {
    P: { label: "Lawful sharing permitted", dissemination: "permitted" },
    C: { label: "Conditions apply", dissemination: "conditional" },
    R: { label: "Recipient restricted", dissemination: "restricted" },
  },
  action_codes: {
    A1: { label: "Covert development", direct_action: false, originator_permission: true },
    A2: { label: "Action permitted", direct_action: true },
  },
  sanitisation_codes: {
    S1: { label: "May be sanitised", consult_originator: false },
    S2: { label: "Consult originator", consult_originator: true },
  },
};

function h(classification: string, handling_code = "P", extra: Partial<Handling> = {}): Handling {
  return { classification, handling_code, originator: "u", owning_unit: "u", ...extra } as Handling;
}

describe("lowerParts", () => {
  it("is empty when nothing is lower, including a raise", () => {
    expect(lowerParts(h("OFFICIAL"), h("SECRET", "R"), SCHEME)).toEqual([]);
    expect(lowerParts(h("SECRET"), h("SECRET"), SCHEME)).toEqual([]);
  });

  it("names each part that is lower", () => {
    const old = h("SECRET", "R", { action_code: "A1", sanitisation_code: "S2" });
    expect(lowerParts(old, h("OFFICIAL", "P"), SCHEME)).toEqual([
      "classification",
      "handling code",
      "action code",
      "sanitisation code",
    ]);
    expect(lowerParts(old, { ...old, action_code: "A2" }, SCHEME)).toEqual(["action code"]);
    expect(lowerParts(h("OFFICIAL", "C"), h("SECRET", "P"), SCHEME)).toEqual(["handling code"]);
  });
});
