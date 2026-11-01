// @vitest-environment jsdom
// ADR-134 decision 1: an alert in a report pack, on the screen and on the printed page — its
// explanation, the entity it matched, its evidence, and its outcome. An open alert says it is open;
// a match no person has confirmed says it is inferred (rule 5). Shared words (`packText`) so the
// screen and the print never disagree.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { packPrintHtml } from "./packExport";
import { PackItemView } from "./PackItemView";
import { alertMatchSentence, alertStatusSentence, itemShortTitle, KIND_LABEL } from "./packText";
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
