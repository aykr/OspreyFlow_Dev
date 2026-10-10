// Whether a link's events are emails (ADR-089, ADR-092). The defect this pins: the Glass read
// `properties.kind`, while the ontology and the Enron loader carry `endpoint_kind`
// (`packages/demo_fixtures/enron.py`), so every Enron link said "Show events" and was never put on
// the canvas as Documents. The node is the one the loader really writes (rule 15).
import { describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { candidateSource, eventsNoun } from "./linkEventsApi";

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

describe("candidateSource", () => {
  // ADR-098 Amendment 1 decision 3: a recogniser gives no score, so its name shows instead of a
  // percentage — and since ADR-108 phase D, spaCy and the transformer recogniser count as
  // recognisers too, not as "100%".
  const candidate = (model: string | undefined, confidence = 1) =>
    ({ id: "c", document_id: "d", entity_type: "Person", properties: {}, confidence, status: "pending", model }) as never;

  it("names each recogniser instead of showing a percentage", () => {
    expect(candidateSource(candidate("stanza:en-1.10"))).toBe("found by Stanza");
    expect(candidateSource(candidate("spacy:en_core_web_sm-3.8.0"))).toBe("found by spaCy");
    expect(candidateSource(candidate("transformers:dslim/bert-base-NER"))).toBe(
      "found by the transformer recogniser",
    );
    expect(candidateSource(candidate("analyst:a1"))).toBe("marked by hand");
  });

  it("shows a model's own confidence as a percentage", () => {
    expect(candidateSource(candidate("qwen2.5:0.5b-instruct", 0.87))).toBe("87%");
  });
});
