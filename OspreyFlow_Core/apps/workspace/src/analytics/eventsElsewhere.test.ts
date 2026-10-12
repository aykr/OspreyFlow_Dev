// ADR-099 Amendment 9: a case with no events of its own says where its datasets' events are — the
// cases the server named, every one, never a sample; nothing when it holds events or none is named.
import { describe, expect, it } from "vitest";

import { eventsElsewhereSentence } from "./eventsElsewhere";

const LEDGER = { investigation_id: "l1", name: "Operation Ledger (synthetic demo)" };

describe("eventsElsewhereSentence", () => {
  it("says nothing for a case that holds events, or when no case the reader can open holds them", () => {
    expect(eventsElsewhereSentence({ has_events: true, held_by: [] })).toBeNull();
    expect(eventsElsewhereSentence({ has_events: true, held_by: [LEDGER] })).toBeNull();
    expect(eventsElsewhereSentence({ has_events: false, held_by: [] })).toBeNull();
    expect(eventsElsewhereSentence(null)).toBeNull();
  });

  it("names the case that holds the events", () => {
    expect(eventsElsewhereSentence({ has_events: false, held_by: [LEDGER] })).toBe(
      "This case holds no events of its own: events stay with the case they were loaded into. " +
        "The events of the datasets it reads are in Operation Ledger (synthetic demo).",
    );
  });

  it("names every holder, and an untitled one as such", () => {
    const three = [LEDGER, { investigation_id: "b", name: "Branch" }, { investigation_id: "u", name: null }];
    expect(eventsElsewhereSentence({ has_events: false, held_by: three })).toMatch(
      /are in Operation Ledger \(synthetic demo\), Branch and an untitled case\.$/,
    );
  });
});
