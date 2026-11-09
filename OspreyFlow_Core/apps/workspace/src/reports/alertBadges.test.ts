// The canvas's alert badge (ADR-146 decision 9): a mark on each item an open alert concerns, from the
// queue the Conduit gave this reader; closed alerts mark nothing.
import { describe, expect, it } from "vitest";

import type { QueuedAlert } from "../../../../packages/schemas/generated";
import { alertBadges } from "./alertBadges";

const row = (id: string, status: string, referents: string[]): QueuedAlert =>
  ({ alert: { id, rule_id: "typology:r", owner_id: "o", mode: "full", created_at: "2026-11-08T00:00:00Z", status, referent_node_ids: referents }, summary: "" }) as QueuedAlert;

describe("the canvas's alert badge", () => {
  it("marks each item an open alert concerns, with how many", () => {
    const badges = alertBadges([
      row("a1", "open", ["n1", "n2"]), row("a2", "claimed", ["n1"]), row("a3", "closing", ["n3", "n3"]),
      row("a4", "closed", ["n4", "n1"]),
    ]);  // prettier-ignore
    expect(Object.fromEntries(badges)).toEqual({
      n1: { text: "!2", label: "2 open alerts" },
      n2: { text: "!", label: "1 open alert" },
      n3: { text: "!", label: "1 open alert" },
    });
  });
});
