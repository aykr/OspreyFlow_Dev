// Whether a link's events are emails (ADR-089, ADR-092). The defect this pins: the Glass read
// `properties.kind`, while the ontology and the Enron loader carry `endpoint_kind`
// (`packages/demo_fixtures/enron.py`), so every Enron link said "Show events" and was never put on
// the canvas as Documents. The node is the one the loader really writes (rule 15).
import { describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { eventsNoun } from "./linkEventsApi";

const enronAddress = makeNode("enron-ep-1", {
  type: "Endpoint",
  properties: { value_raw: "a@enron.com", value_normalised: "a@enron.com", endpoint_kind: "email" },
});
const phone = makeNode("cdr-ep-1", {
  type: "Endpoint",
  properties: { value_raw: "07911123456", value_normalised: "+447911123456", endpoint_kind: "msisdn" },
});
const paysimAccount = makeNode("paysim-acct-1", {
  type: "Endpoint",
  properties: { value_normalised: "C1305486145", endpoint_kind: "account" },
});

describe("eventsNoun", () => {
  it("calls the events between two email addresses emails", () => {
    expect(eventsNoun("COMMUNICATED_WITH", enronAddress)).toBe("emails");
  });

  it("calls the events between two phones messages (ADR-094)", () => {
    expect(eventsNoun("COMMUNICATED_WITH", phone)).toBe("messages");
  });

  it("calls anything else events", () => {
    expect(eventsNoun("TRANSACTED", paysimAccount)).toBe("events");
    expect(eventsNoun("COMMUNICATED_WITH", paysimAccount)).toBe("events");
    expect(eventsNoun("COMMUNICATED_WITH", undefined)).toBe("events");
  });
});
