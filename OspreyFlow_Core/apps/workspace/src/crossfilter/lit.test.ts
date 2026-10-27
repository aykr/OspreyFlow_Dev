import { describe, expect, it } from "vitest";

import type { FirstSeen } from "./emergence";
import { litNote, litSet, litTabName, UNDATED_NOT_INCLUDED, type LitLink } from "./lit";

// ADR-128 decision 2 (B3). A link is lit when at least one of its events falls inside the window,
// ends included; an undated link is never lit; a node is lit when a lit link touches it. What the
// server answers (`first_seen`) is the earliest event in the window per link, so a link is lit when
// it has an answer and the answer lies inside the window.

const window = { validFrom: "2026-01-05T00:00:00Z", validTo: "2026-04-30T23:59:59Z" };

const links: LitLink[] = [
  { id: "inside", source: "a", target: "b" },
  { id: "first-instant", source: "b", target: "c" },
  { id: "last-instant", source: "c", target: "d" },
  { id: "undated", source: "e", target: "f" },
  { id: "outside", source: "g", target: "h" },
];

const firstSeen: FirstSeen = {
  nodes: {},
  edges: {
    inside: "2026-02-01T10:00:00Z",
    "first-instant": "2026-01-05T00:00:00Z",
    "last-instant": "2026-04-30T23:59:59Z",
    // `undated` has no event at all, so the server gives it no answer.
    outside: "2026-06-01T00:00:00Z",
  },
};

describe("litSet", () => {
  it("lights a link with an event inside the window, the window's own ends included", () => {
    const lit = litSet(firstSeen, window, links);
    expect(lit.edgeIds).toEqual(["inside", "first-instant", "last-instant"]);
  });

  it("never lights an undated link, so nodes only it touches are not lit", () => {
    const lit = litSet(firstSeen, window, links);
    expect(lit.edgeIds).not.toContain("undated");
    expect(lit.nodeIds).not.toContain("e");
    expect(lit.nodeIds).not.toContain("f");
  });

  it("lights a node when a lit link touches it, once, in the order the links give", () => {
    const lit = litSet(firstSeen, window, links);
    expect(lit.nodeIds).toEqual(["a", "b", "c", "d"]);
  });

  it("does not light a link whose answer lies outside the window, whatever the server said", () => {
    const lit = litSet(firstSeen, window, links);
    expect(lit.edgeIds).not.toContain("outside");
    expect(lit.nodeIds).not.toContain("g");
  });

  it("takes a window with no end as running on without end", () => {
    const open = litSet(firstSeen, { validFrom: "2026-01-05T00:00:00Z", validTo: null }, links);
    expect(open.edgeIds).toContain("outside");
  });

  it("lights nothing from an answer that names links the view does not hold", () => {
    const lit = litSet({ nodes: {}, edges: { ghost: "2026-02-01T00:00:00Z" } }, window, links);
    expect(lit).toEqual({ nodeIds: [], edgeIds: [] });
  });

  it("says in words that undated links are not included", () => {
    expect(UNDATED_NOT_INCLUDED).toBe("undated links are not included");
  });
});

describe("litTabName", () => {
  it("names the tab from the window, the year once when both ends share it", () => {
    expect(
      litTabName({ validFrom: "2026-01-05T00:00:00Z", validTo: "2026-04-30T23:59:59Z" }),
    ).toBe("5 Jan – 30 Apr 2026, selected");
  });

  it("names the day the window's end falls on, because the end is lit: an end at midnight is that day", () => {
    // `litSet` includes an event at exactly the end, so a window ending at 1 May 00:00 lights
    // 1 May's first instant and must not be labelled as if it stopped on 30 Apr.
    expect(litSet({ nodes: {}, edges: { x: "2026-05-01T00:00:00Z" } }, { validFrom: "2026-01-05T00:00:00Z", validTo: "2026-05-01T00:00:00Z" }, [
      { id: "x", source: "a", target: "b" },
    ]).edgeIds).toEqual(["x"]);
    expect(
      litTabName({ validFrom: "2026-01-05T00:00:00Z", validTo: "2026-05-01T00:00:00Z" }),
    ).toBe("5 Jan – 1 May 2026, selected");
  });

  it("gives both years when the window crosses a year", () => {
    expect(
      litTabName({ validFrom: "2025-11-01T00:00:00Z", validTo: "2026-02-01T00:00:00Z" }),
    ).toBe("1 Nov 2025 – 1 Feb 2026, selected");
  });

  it("names a window within one day by its day", () => {
    expect(
      litTabName({ validFrom: "2026-03-02T09:00:00Z", validTo: "2026-03-02T17:00:00Z" }),
    ).toBe("2 Mar 2026, selected");
  });

  it("names a window with no end by where it starts", () => {
    expect(litTabName({ validFrom: "2026-03-02T00:00:00Z", validTo: null })).toBe(
      "From 2 Mar 2026, selected",
    );
  });
});

describe("litNote, the sentence beside what is lit", () => {
  it("reads a window with two ends as 'Lit in <range>'", () => {
    expect(litNote({ validFrom: "2026-01-05T00:00:00Z", validTo: "2026-04-30T23:59:59Z" })).toBe(
      `Lit in 5 Jan – 30 Apr 2026: ${UNDATED_NOT_INCLUDED}`,
    );
  });

  it("reads an open-ended window as 'Lit from <date>', not 'Lit in From <date>'", () => {
    expect(litNote({ validFrom: "2026-01-05T00:00:00Z", validTo: null })).toBe(
      `Lit from 5 Jan 2026: ${UNDATED_NOT_INCLUDED}`,
    );
  });

  it("names a single day as 'Lit on <day>'", () => {
    expect(litNote({ validFrom: "2026-03-02T09:00:00Z", validTo: "2026-03-02T17:00:00Z" })).toBe(
      `Lit on 2 Mar 2026: ${UNDATED_NOT_INCLUDED}`,
    );
  });
});

