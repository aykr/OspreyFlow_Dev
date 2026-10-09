// @vitest-environment jsdom
// ADR-098 Amendment 1: a pending finding is drawn in the text only where its locator's words
// hash to its own excerpt_hash — never where the locator merely points.
import { describe, expect, it } from "vitest";

import type { EmailCandidate } from "../inspector/linkEventsApi";
import { pendingSpansIn } from "./pendingSpans";

const TEXT = "Dana MERCER wrote to SRP about the plant.";

//: sha256 of the exact words a span covers.
async function hashOf(words: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(words));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function candidate(partial: Partial<EmailCandidate> & { locator?: string }): Promise<EmailCandidate> {
  return {
    id: "c1",
    document_id: "d1",
    entity_type: "Person",
    properties: {},
    confidence: 0.9,
    status: "pending",
    locator: "char span 0-11",
    excerpt_hash: await hashOf("Dana MERCER"),
    ...partial,
  };
}

describe("pendingSpansIn", () => {
  it("locates a pending finding whose words are at the locator's place", async () => {
    const spans = await pendingSpansIn(TEXT, [await candidate({})]);
    expect(spans).toEqual([{ start: 0, end: 11, entity_type: "Person" }]);
  });

  it("drops a span whose words are not what the extractor matched", async () => {
    const wrong = await candidate({ excerpt_hash: await hashOf("someone else") });
    expect(await pendingSpansIn(TEXT, [wrong])).toEqual([]);
  });

  it("drops a span beyond the shown text, an accepted finding, and one with no locator", async () => {
    const beyond = await candidate({ locator: `char span 10-${TEXT.length + 40}` });
    const accepted = await candidate({ status: "accepted" });
    const unlocated = await candidate({ locator: undefined, excerpt_hash: undefined });
    expect(await pendingSpansIn(TEXT, [beyond, accepted, unlocated])).toEqual([]);
  });

  it("keeps the first of two overlapping spans and sorts by place", async () => {
    const late = await candidate({
      id: "c2",
      entity_type: "Organisation",
      locator: "char span 21-24",
      excerpt_hash: await hashOf("SRP"),
    });
    const overlapping = await candidate({ id: "c3", locator: "char span 5-11", excerpt_hash: await hashOf("MERCER") });
    const spans = await pendingSpansIn(TEXT, [late, await candidate({}), overlapping]);
    expect(spans).toEqual([
      { start: 0, end: 11, entity_type: "Person" },
      { start: 21, end: 24, entity_type: "Organisation" },
    ]);
  });
});
