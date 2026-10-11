// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EntityTypeDef, Node } from "../../../../packages/schemas/generated";
import {
  LABEL_CHOICES_KEY,
  chosenLabel,
  defaultLabel,
  forgetLabelChoicesForTest,
  getLabelChoices,
  labelPropertiesFor,
  onLabelChoicesChange,
  setLabelChoice,
} from "./labelChoices";
import { nodeLabel } from "./nodeAttributes";

// ADR-076. The analyst picks which property names a node of each type. It is a way of looking, so it
// is kept in this browser only, never sent to the server and not part of the case (as the theme is).

function node(type: string, properties: Record<string, unknown>, id = "n1"): Node {
  return { id, type, properties } as unknown as Node;
}

const volkov = node("Person", {
  nino: "QQ118439C",
  family_name: "Volkov",
  given_names: "Mikhail",
  date_of_birth: "1975-03-12",
});

beforeEach(() => {
  localStorage.clear();
  forgetLabelChoicesForTest();
});
afterEach(() => vi.restoreAllMocks());

describe("a rule's alert on the canvas", () => {
  it("is named by what the rule found, never by its id (rule 7)", () => {
    // Found live, 11 October 2026: an alert shown on the canvas read "01M4MQZPCS31…WFRXQ1ZXP0H".
    const alert = node("Alert", { rule_id: "typology:01M4", typology: "kyc_screening", words: "…" }, "01M4MQZPCS31");
    expect(defaultLabel(alert)).toBe("KYC screening alert");
    expect(defaultLabel(node("Alert", { rule_id: "typology:x" }))).toBe("Alert");
  });
});

describe("the default label", () => {
  it("is the family name then the given names for a person, so people of one family differ", () => {
    expect(defaultLabel(volkov)).toBe("Volkov, Mikhail");
    expect(nodeLabel(volkov)).toBe("Volkov, Mikhail");
  });

  it("is just the family name when a person has no given names", () => {
    expect(nodeLabel(node("Person", { family_name: "Volkov" }))).toBe("Volkov");
  });

  it("is the normalised value for a thing that has one, and the id when there is nothing", () => {
    expect(nodeLabel(node("Endpoint", { value_normalised: "a@b.test" }))).toBe("a@b.test");
    // A named thing is called by its name (owner, 6 October 2026); only a thing with nothing is its id.
    expect(nodeLabel(node("Organisation", { name: "Ring 0 Holdings" }, "org-1"))).toBe("Ring 0 Holdings");
    expect(nodeLabel(node("Organisation", {}, "org-1"))).toBe("org-1");
  });
});

describe("a chosen label", () => {
  it("replaces the default for that type only", () => {
    setLabelChoice("Organisation", "name");
    setLabelChoice("Person", "nino");
    expect(nodeLabel(volkov)).toBe("QQ118439C");
    expect(nodeLabel(node("Organisation", { name: "Ring 0 Holdings" }, "org-1"))).toBe("Ring 0 Holdings");
    expect(nodeLabel(node("Endpoint", { value_normalised: "a@b.test" }))).toBe("a@b.test");
  });

  it("falls back to the default for a node that lacks the chosen property, never a blank label", () => {
    setLabelChoice("Person", "nino");
    expect(nodeLabel(node("Person", { family_name: "Volkov", given_names: "Mikhail" }))).toBe("Volkov, Mikhail");
    expect(nodeLabel(node("Person", { nino: "", family_name: "Volkov" }))).toBe("Volkov");
  });

  it("shows a number as text", () => {
    setLabelChoice("Account", "balance_band");
    expect(nodeLabel(node("Account", { balance_band: 3 }))).toBe("3");
  });

  it("is forgotten when it is cleared", () => {
    setLabelChoice("Person", "nino");
    setLabelChoice("Person", null);
    expect(nodeLabel(volkov)).toBe("Volkov, Mikhail");
    expect(getLabelChoices()).toEqual({});
  });

  it("is reported by chosenLabel only when one applies", () => {
    expect(chosenLabel(volkov)).toBeNull();
    setLabelChoice("Person", "given_names");
    expect(chosenLabel(volkov)).toBe("Mikhail");
  });
});

describe("keeping the choice in this browser", () => {
  it("writes it under one key, as plain JSON", () => {
    setLabelChoice("Person", "nino");
    expect(JSON.parse(localStorage.getItem(LABEL_CHOICES_KEY) ?? "null")).toEqual({ Person: "nino" });
  });

  it("is read back after a reload", () => {
    localStorage.setItem(LABEL_CHOICES_KEY, JSON.stringify({ Person: "nino" }));
    forgetLabelChoicesForTest();
    expect(nodeLabel(volkov)).toBe("QQ118439C");
  });

  it("ignores stored text that is not a choice, and keeps working", () => {
    for (const bad of ["not json", "[1,2]", "null", '{"Person":42}', '{"Person":""}']) {
      localStorage.setItem(LABEL_CHOICES_KEY, bad);
      forgetLabelChoicesForTest();
      expect(getLabelChoices()).toEqual({});
      expect(nodeLabel(volkov)).toBe("Volkov, Mikhail");
    }
  });

  it("still works for this page when the browser will not store anything", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    forgetLabelChoicesForTest();
    setLabelChoice("Person", "nino");
    expect(nodeLabel(volkov)).toBe("QQ118439C");
  });
});

describe("telling the canvas", () => {
  it("calls a listener when a choice changes, and not after it is removed", () => {
    const heard = vi.fn();
    const stop = onLabelChoicesChange(heard);
    setLabelChoice("Person", "nino");
    expect(heard).toHaveBeenCalledTimes(1);
    stop();
    setLabelChoice("Person", null);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("does not call a listener when the choice is unchanged", () => {
    setLabelChoice("Person", "nino");
    const heard = vi.fn();
    onLabelChoicesChange(heard);
    setLabelChoice("Person", "nino");
    setLabelChoice("Organisation", null);
    expect(heard).not.toHaveBeenCalled();
  });
});

describe("the properties offered for a type", () => {
  const person: EntityTypeDef = {
    name: "Person",
    pole_class: "person",
    channel: "indigo",
    shape: "circle",
    identifiers: ["nino"],
    properties: [
      { name: "family_name", type: "string", indexed: true },
      { name: "given_names", type: "string", indexed: true },
      { name: "date_of_birth", type: "date", sensitivity: "high" },
      { name: "aliases", type: "string[]" },
      { name: "nino", type: "string", indexed: true },
    ],
  };

  it("are its identifiers and properties, each once, without a sensitive or a list property", () => {
    expect(labelPropertiesFor(person)).toEqual(["nino", "family_name", "given_names"]);
  });

  it("are empty for a type with none", () => {
    expect(labelPropertiesFor({ ...person, identifiers: [], properties: [] })).toEqual([]);
  });
});

// Owner, 6 October 2026: an extracted organisation was drawn as its id ("01M48S26W58A…") although it
// is called BPA, and an email Document as "email:enron-…". A thing with a name or a title is called by it.
describe("defaultLabel names a thing by its name or title before its identifiers", () => {
  const n = (type: string, properties: Record<string, unknown>) =>
    ({ id: "01M48S26W58AM0WCX9AE3BG0VQ", type, properties }) as unknown as Node;

  it("an organisation or a place by its name", () => {
    expect(defaultLabel(n("Organisation", { name: "BPA" }))).toBe("BPA");
    expect(defaultLabel(n("Location", { name: "Houston" }))).toBe("Houston");
  });

  it("a document by its title, before its normalised value", () => {
    expect(defaultLabel(n("Document", { title: "Urgent - Drugs Test Reminder", value_normalised: "email:enron-1" }))).toBe(
      "Urgent - Drugs Test Reminder",
    );
  });

  it("still a person by family and given names, an address by its value, and the id as the last resort", () => {
    expect(defaultLabel(n("Person", { family_name: "Lay", given_names: "Kenneth", name: "Ken" }))).toBe("Lay, Kenneth");
    expect(defaultLabel(n("Endpoint", { value_normalised: "richard.ring@enron.com" }))).toBe("richard.ring@enron.com");
    expect(defaultLabel(n("Vehicle", {}))).toBe("01M48S26W58AM0WCX9AE3BG0VQ");
  });
});
