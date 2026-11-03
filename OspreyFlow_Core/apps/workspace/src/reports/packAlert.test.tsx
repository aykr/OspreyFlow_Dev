// @vitest-environment jsdom
// ADR-134 decision 1: an alert in a report pack, on the screen and on the printed page — its
// explanation, the entity it matched, its evidence, and its outcome. An open alert says it is open;
// a match no person has confirmed says it is inferred (rule 5). Shared words (`packText`) so the
// screen and the print never disagree.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { packPrintHtml } from "./packExport";
import { PackItemView } from "./PackItemView";
import { alertMatchSentence, alertStatusSentence, itemShortTitle, KIND_LABEL, WITHHELD_ITEMS_SENTENCE } from "./packText";
import { ALERT_ITEM, CLOSED_ALERT_ITEM, manifest } from "./reportsTestKit";

afterEach(cleanup);

describe("the words an alert item is said in", () => {
  it("says an open alert is open and a match nobody confirmed is inferred", () => {
    expect(alertStatusSentence(ALERT_ITEM.alert!)).toBe("Open: not yet decided when this was added.");
    expect(alertMatchSentence(ALERT_ITEM.alert!)).toBe("Inferred: no one has confirmed this match.");
  });

  it("says a closed alert's outcome and reason, and a confirmed match", () => {
    expect(alertStatusSentence(CLOSED_ALERT_ITEM.alert!)).toBe("Closed as True match: Confirmed with the bank.");
    expect(alertStatusSentence({ ...CLOSED_ALERT_ITEM.alert!, outcome: "duplicate" })).toBe("Closed as Duplicate: Confirmed with the bank.");
    expect(alertMatchSentence(CLOSED_ALERT_ITEM.alert!)).toBe("Confirmed by a person.");
    expect(alertStatusSentence({ ...ALERT_ITEM.alert!, status: "claimed" })).toBe("Open, being worked on, when this was added.");
    expect(alertStatusSentence({ ...ALERT_ITEM.alert!, status: "closed", outcome: null, reason: "Taken back with its load" })).toBe(
      "Closed without an outcome: Taken back with its load.",
    );
  });

  // Build order step 15: the Ledger pack read "…citing the circle through Crescent.." — the close
  // reason as the analyst typed it ends with a full stop, and the sentence added another.
  it("never doubles the full stop when the reason already ends a sentence", () => {
    const closed = { ...CLOSED_ALERT_ITEM.alert!, outcome: "referred" as const };
    expect(alertStatusSentence({ ...closed, reason: "To the MLRO: citing the circle through Crescent." })).toBe(
      "Closed as Referred: To the MLRO: citing the circle through Crescent.",
    );
    expect(alertStatusSentence({ ...closed, reason: "Is it the same ring?" })).toBe("Closed as Referred: Is it the same ring?");
    expect(alertStatusSentence({ ...closed, reason: "Sent on!  " })).toBe("Closed as Referred: Sent on!");
    expect(alertStatusSentence({ ...closed, status: "closed", outcome: null, reason: "Taken back." })).toBe(
      "Closed without an outcome: Taken back.",
    );
  });

  // Build order step 15: the Ledger pack said "Some items … withheld from you" to the analyst who had
  // added them. Nothing was withheld from her: the revert of the week's load had taken back R1's own
  // Alert node, which the item cites, so the item is rightly not shown — for a reason the sentence
  // denied. The sentence says both reasons, and still never which item, how many, or which reason.
  it("says an item is not shown without claiming it is held back from this reader alone", () => {
    expect(WITHHELD_ITEMS_SENTENCE).toBe(
      "Some items of this pack are not shown to you: you may not see something they rest on, or it has since been taken back.",
    );
    expect(WITHHELD_ITEMS_SENTENCE).not.toMatch(/\d/);
  });

  it("names the item kind and gives it a short title", () => {
    expect(KIND_LABEL.alert).toBe("Alert");
    expect(itemShortTitle(ALERT_ITEM)).toBe("Money in and straight out again through Halcyon Marine Ltd");
  });
});

describe("an alert item on the screen", () => {
  it("shows its explanation, its entity, its evidence, its status and its match", () => {
    render(<PackItemView item={ALERT_ITEM} />);
    const item = screen.getByRole("article", { name: "Alert: Money in and straight out again through Halcyon Marine Ltd" });
    const text = item.textContent ?? "";
    expect(text).toContain("Marked OFFICIAL");
    expect(text).toContain("Open: not yet decided when this was added.");
    expect(text).toContain("Inferred: no one has confirmed this match.");
    expect(within(item).getByRole("list", { name: "Entities it matched" }).textContent).toContain("Halcyon Marine Ltd");
    expect(within(item).getByRole("list", { name: "Evidence" }).textContent).toContain("£9,500");
    expect(text).toContain("High severity");
  });
});

describe("an alert item on the printed page", () => {
  it("prints its status and its match, escaped, under its own marking", () => {
    const html = packPrintHtml(manifest([ALERT_ITEM, CLOSED_ALERT_ITEM]));
    const [open, closed] = html.split('<section class="page item"').slice(1) as [string, string];
    expect(open).toContain("Open: not yet decided when this was added.");
    expect(open).toContain("Inferred: no one has confirmed this match.");
    expect(open.match(/Marked OFFICIAL/g)).toHaveLength(2);
    expect(closed).toContain("Closed as True match: Confirmed with the bank.");
    expect(closed).toContain("Halcyon Marine Ltd");
  });
});

describe("an alert trend in words", () => {
  it("counts alerts, not events", async () => {
    const { trendSentence } = await import("./packText");
    const { figures } = await import("./reportsTestKit");
    const f = figures({ source: "alerts", event_types: [], measure: "count", measure_field: null });
    expect(trendSentence({ ...f, result: { ...f.result, measure: "count", events: 1 } })).toBe("1 alert in 12 weeks");
    expect(trendSentence({ ...f, result: { ...f.result, measure: "count", events: 54 } })).toBe("54 alerts in 12 weeks");
  });
});

describe("a screening alert's list entry (step 9e)", () => {
  // The alert cites the customer and the list's own entry for the listed party, never merged
  // (rule 6); the stored item says which is the list's (`list_entry_on`), so a pack read later
  // does not show one person matched twice.
  const SCREENED = {
    ...ALERT_ITEM,
    alert: {
      ...ALERT_ITEM.alert!,
      entities: [
        { node_id: "n-customer", entity_type: "Person", name: "Sofia Ruiz" },
        { node_id: "n-listed", entity_type: "Person", name: "Sofia Ruiz", list_entry_on: "UK Sanctions List (synthetic)" },
      ],
    },
  };
  const LINES = ["Sofia Ruiz (Person)", "Sofia Ruiz (Person) · the entry on UK Sanctions List (synthetic)"];

  it("is named as the list's on the screen", () => {
    render(<PackItemView item={SCREENED} />);
    const list = screen.getByRole("list", { name: "Entities it matched" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(LINES);
  });

  it("is named as the list's on the printed page", () => {
    const html = packPrintHtml(manifest([SCREENED]));
    for (const line of LINES) expect(html).toContain(`<li>${line}</li>`);
  });
});
