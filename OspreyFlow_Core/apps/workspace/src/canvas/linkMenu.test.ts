import { describe, expect, it } from "vitest";

import { makeEdge } from "../testing/fixtures";
import { linkMenuItems, linkMenuTitle, type LinkMenuActions } from "./linkMenu";

function actions(): { calls: string[]; actions: LinkMenuActions } {
  const calls: string[] = [];
  const record = (name: string) => () => {
    calls.push(name);
  };
  return {
    calls,
    actions: {
      onCollapse: record("collapse"),
      onExpand: record("expand"),
      onConfirm: record("confirm"),
      onNotSame: record("not-same"),
      onExplain: record("explain"),
      onNote: record("note"),
      onHide: record("hide"),
      onChange: record("change"),
      onHistory: record("history"),
    },
  };
}

const ids = (items: { id: string }[]) => items.map((i) => i.id);

describe("linkMenuItems", () => {
  it("offers a same-as link the six things the analyst asked for, in a sensible order", () => {
    const { actions: a } = actions();
    const items = linkMenuItems(makeEdge("e1", "a", "b", { type: "SAME_AS" }), false, a);
    expect(ids(items)).toEqual([
      "link-collapse",
      "link-confirm",
      "link-not-same",
      "link-explain",
      "link-note",
      "link-hide",
    ]);
    expect(items.map((i) => i.label)).toEqual([
      "Collapse into one node",
      "Confirm as the same",
      "Mark as not the same",
      "Explain this link",
      "Add a note",
      "Hide link",
    ]);
  });

  it("says Expand, not Collapse, once the nodes are folded", () => {
    const { actions: a, calls } = actions();
    const items = linkMenuItems(makeEdge("e1", "a", "b", { type: "SAME_AS" }), true, a);
    expect(items[0]).toMatchObject({ id: "link-expand", label: "Expand" });
    items[0]!.onSelect();
    expect(calls).toEqual(["expand"]);
  });

  it("offers any other link a change, its history, a note and hiding — and no same-as actions", () => {
    const { actions: a } = actions();
    const items = linkMenuItems(makeEdge("e1", "a", "b", { type: "ASSOCIATE_OF" }), false, a);
    expect(ids(items)).toEqual(["link-change", "link-history", "link-note", "link-hide"]);
    expect(items.map((i) => i.label)).toEqual([
      "Change link…",
      "Show change history",
      "Add a note",
      "Hide link",
    ]);
  });

  it("leaves a not-the-same link to notes and hiding: it is not edited by hand", () => {
    const { actions: a } = actions();
    const items = linkMenuItems(makeEdge("e1", "a", "b", { type: "NOT_SAME_AS" }), false, a);
    expect(ids(items)).toEqual(["link-note", "link-hide"]);
  });

  it("calls the matching action when an entry is chosen", () => {
    const { actions: a, calls } = actions();
    const same = linkMenuItems(makeEdge("e1", "a", "b", { type: "SAME_AS" }), false, a);
    for (const item of same) item.onSelect();
    expect(calls).toEqual(["collapse", "confirm", "not-same", "explain", "note", "hide"]);
    calls.length = 0;
    const other = linkMenuItems(makeEdge("e2", "a", "b"), false, a);
    for (const item of other) item.onSelect();
    expect(calls).toEqual(["change", "history", "note", "hide"]);
  });

  it("draws no count against any entry, and groups them so the list reads in sections", () => {
    const { actions: a } = actions();
    for (const type of ["SAME_AS", "ASSOCIATE_OF", "NOT_SAME_AS"]) {
      const items = linkMenuItems(makeEdge("e1", "a", "b", { type }), false, a);
      expect(items.every((i) => i.count === undefined)).toBe(true);
      expect(items.every((i) => typeof i.group === "string" && i.group.length > 0)).toBe(true);
    }
  });
});

describe("linkMenuTitle", () => {
  it("names the link by its type and its two ends", () => {
    expect(linkMenuTitle("SAME_AS", "Person: Ada", "Person: A. Lovelace")).toBe(
      "SAME_AS: Person: Ada ↔ Person: A. Lovelace",
    );
  });
});

// ADR-089: an ordinary link offers the events behind it first, named for what they are.
describe("the events entry (ADR-089)", () => {
  it("is offered first on an ordinary link when a label is given, and not without one", () => {
    const calls: string[] = [];
    const actions = {
      onCollapse: () => calls.push("collapse"),
      onExpand: () => calls.push("expand"),
      onConfirm: () => calls.push("confirm"),
      onNotSame: () => calls.push("not-same"),
      onExplain: () => calls.push("explain"),
      onNote: () => calls.push("note"),
      onHide: () => calls.push("hide"),
      onChange: () => calls.push("change"),
      onHistory: () => calls.push("history"),
    };
    const edge = makeEdge("ln0", "a", "b", { type: "COMMUNICATED_WITH", occurrences: 12 });
    const withEvents = linkMenuItems(edge, false, {
      ...actions,
      onEvents: () => calls.push("events"),
      eventsLabel: "Show emails (12)",
    });
    expect(withEvents.map((i) => i.id)[0]).toBe("link-events");
    expect(withEvents[0]!.label).toBe("Show emails (12)");
    withEvents[0]!.onSelect();
    expect(calls).toEqual(["events"]);
    expect(linkMenuItems(edge, false, actions).map((i) => i.id)).toEqual([
      "link-change",
      "link-history",
      "link-note",
      "link-hide",
    ]);
  });

  it("is never offered on a same-as or a not-the-same link", () => {
    const quiet = () => undefined;
    const actions = {
      onCollapse: quiet, onExpand: quiet, onConfirm: quiet, onNotSame: quiet, onExplain: quiet,
      onNote: quiet, onHide: quiet, onChange: quiet, onHistory: quiet, onEvents: quiet, eventsLabel: "Show events (1)",
    };
    expect(linkMenuItems(makeEdge("sa", "a", "b", { type: "SAME_AS" }), false, actions).map((i) => i.id)).not.toContain("link-events");
    expect(linkMenuItems(makeEdge("ns", "a", "b", { type: "NOT_SAME_AS" }), false, actions).map((i) => i.id)).not.toContain("link-events");
  });
});
