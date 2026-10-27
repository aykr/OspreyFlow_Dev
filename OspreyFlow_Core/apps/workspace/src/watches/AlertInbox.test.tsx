// @vitest-environment jsdom
//
// Render-layer tests for `AlertInbox`'s two named Stage 6c Part 2 requirements. Component
// rendering has no prior precedent in this workspace's `vitest` suite (every existing
// `*.test.ts` is pure-logic, `environment: "node"`, no `@testing-library/react`) — the
// per-file `@vitest-environment jsdom` docblock above opts only this file into a DOM
// environment rather than changing `vitest.config.ts`'s own global default, so every other
// test's `environment: "node"` is unaffected.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { AlertRow, JumpResultSummary } from "./AlertInbox";
import type { AlertJumpResult, AlertView } from "./api";

afterEach(() => {
  cleanup();
});

const NOTIFY_ALERT: AlertView = {
  id: "alert-1",
  rule_id: "hotlist:hl-1",
  owner_id: "analyst-1",
  mode: "notify_stub",
  referent_node_ids: [],
  evidence_available: false,
  investigation_id: null,
  created_at: "2026-09-22T00:00:00Z",
};

describe("test_a_notify_mode_alert_renders_with_no_referent_the_viewer_cannot_read", () => {
  test("a notify-mode alert renders with no referent the viewer cannot read", () => {
    // The fixture's own `referent_node_ids` is `[]` and `rule_id` carries no identifier
    // (`hotlist:hl-1` names the hotlist, not the match) — proving this requires more than
    // asserting the fixture is empty, since that only proves the *fixture*, not the renderer.
    // The real claim: `AlertRow` does not reconstruct, fetch, or otherwise surface identifying
    // detail from anywhere else once handed a redacted `notify_stub` view. A node-id shape a
    // real `referent_node_ids` entry would take (this codebase's own `new_id()` — a bare
    // lowercase-hex/uuid-ish token) appears nowhere in the rendered output if this holds.
    const { container } = render(
      <ul>
        <AlertRow alert={NOTIFY_ALERT} onJump={() => undefined} jumping={false} />
      </ul>,
    );

    const text = container.textContent ?? "";
    expect(text).toContain("A match fired — no evidence visible to you.");
    expect(container.querySelectorAll("li li")).toHaveLength(0); // no referent list rendered
    expect(text).not.toMatch(/[0-9a-f]{8,}/i); // no id-shaped token anywhere in the row
  });

  test("reverting the redaction (rendering referents on a notify_stub alert) fails this test", () => {
    // Proves the test above is load-bearing, not vacuous: an `AlertRow` that ignored `mode` and
    // rendered `referent_node_ids` unconditionally would still pass the first test (the fixture's
    // own list is empty) — this second case feeds a *non-empty* `referent_node_ids` on a
    // `notify_stub` alert (a shape the real server-side `AlertView` never actually produces,
    // `alert_to_view`'s own redaction guarantees that) specifically to prove the component itself
    // is what enforces "notify_stub never shows a referent", not merely an accident of the
    // fixtures used above.
    const leaking: AlertView = { ...NOTIFY_ALERT, referent_node_ids: ["node-should-not-render"] };
    const { container } = render(
      <ul>
        <AlertRow alert={leaking} onJump={() => undefined} jumping={false} />
      </ul>,
    );
    // `AlertRow`'s own `hasReferents` guard is `alert.mode === "full" && ...` — a `notify_stub`
    // alert never satisfies it regardless of what `referent_node_ids` carries, so this still
    // renders nothing. Asserted explicitly here so a future change to that guard (e.g. dropping
    // the `mode === "full"` half) is caught by this file, not only by trusting the server's own
    // redaction never to be bypassed.
    expect(container.textContent ?? "").not.toContain("node-should-not-render");
  });
});

// ADR-124 decision 1: the jump summary carries no count of what the reader cannot read. A server
// that still sends `unreadable_count` has it ignored.
const JUMP_RESULT = {
  investigation: {
    id: "inv-branch-1",
    created_at: "2026-09-22T00:00:00Z",
    created_by: "analyst-1",
    owning_unit: "unit-1",
    branched_from: "inv-source-1",
  },
  seeded_count: 3,
  unreadable_count: 2,
} as unknown as AlertJumpResult;

describe("test_jump_result_shows_no_unreadable_count", () => {
  test("the jump summary says how many were added and nothing of what could not be read", () => {
    const { container, queryByTestId } = render(
      <JumpResultSummary result={JUMP_RESULT} onOpen={() => undefined} />,
    );
    expect(queryByTestId("jump-unreadable-summary")).toBeNull();
    expect(container.textContent ?? "").toContain("3 entities added to the new investigation.");
    expect(container.textContent ?? "").not.toMatch(/referent|accessible|unreadable|\b2\b/);
  });
});

// ADR-110 decision 10, Amendment 3: a notice that a scheduled run failed or was refused reads as
// its words — not as a match whose evidence vanished, and with nothing to jump into.
describe("a schedule notice", () => {
  const NOTICE: AlertView = {
    id: "n1", rule_id: "schedule:recipe-1", owner_id: "approver-1", mode: "full", referent_node_ids: [],
    evidence_available: true, investigation_id: "case-1", created_at: "2026-06-02T05:00:00Z",
    words: "The scheduled run of Daily export due 2 June 2026 at 06:00 was refused: the owner can no longer sign in",
  };  // prettier-ignore

  test("reads as its words, with no evidence line and no jump", () => {
    const { container, queryByRole } = render(
      <ul>
        <AlertRow alert={NOTICE} onJump={() => undefined} jumping={false} />
      </ul>,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Scheduled run");
    expect(text).toContain("was refused: the owner can no longer sign in");
    expect(text).not.toContain("Evidence no longer available");
    expect(queryByRole("button", { name: /Jump/ })).toBeNull();
  });
});

// ADR-130 decision 1: a hotlist alert explains itself in the words the owner knows, and shows
// neither the raw rule id nor a node id.
describe("a hotlist alert that explains itself", () => {
  const EXPLAINED: AlertView = {
    id: "alert-9", rule_id: "hotlist:01HZX3Q9K2M5N7P8R0S1T2V3W4", owner_id: "analyst-1", mode: "full",
    referent_node_ids: ["01HZX3Q9K2M5N7P8R0S1T2V3W5"], evidence_available: true,
    investigation_id: "case-1", created_at: "2026-10-02T09:00:00Z",
    hotlist: { identifier: "07700 900640", kept_as_written: false, review_date: "2027-01-31" },
    fired_on: [
      {
        type: "Endpoint", label: "+447700900640", more_files: 0,
        files: [
          { name: "pid_seized_comms_batch2.csv", row: 3 },
          { name: "pid_pin_calls.csv", rows: 2013 },
        ],
      },
    ],
  };  // prettier-ignore

  function text(alert: AlertView): string {
    const { container } = render(
      <ul>
        <AlertRow alert={alert} onJump={() => undefined} jumping={false} />
      </ul>,
    );
    return container.textContent ?? "";
  }

  test("reads the hotlist, what matched and where it was read from", () => {
    const t = text(EXPLAINED);
    expect(t).toContain("Hotlist: 07700 900640 · review by 31 Jan 2027");
    expect(t).toContain("Matched: Endpoint +447700900640");
    expect(t).toContain("From: pid_seized_comms_batch2.csv, row 3; pid_pin_calls.csv, 2,013 rows");
  });

  test("shows neither the raw rule id nor a node id, and keeps the jump", () => {
    const { container, getByRole } = render(
      <ul>
        <AlertRow alert={EXPLAINED} onJump={() => undefined} jumping={false} />
      </ul>,
    );
    const t = container.textContent ?? "";
    expect(t).not.toContain("hotlist:");
    expect(t).not.toContain("01HZX3Q9K2M5N7P8R0S1T2V3W");
    expect(getByRole("button", { name: "Jump into investigation" })).toBeTruthy();
  });

  test("says how many more files, never cutting silently", () => {
    const more: AlertView = {
      ...EXPLAINED,
      fired_on: [{ type: "Endpoint", label: "+447700900640", more_files: 3,
                   files: [{ name: "a.csv", row: 1 }] }],
    };  // prettier-ignore
    expect(text(more)).toContain("From: a.csv, row 1; and 3 more files");
    const first = (more.fired_on ?? [])[0];
    if (!first) throw new Error("fixture has no fired_on");
    const one: AlertView = { ...more, fired_on: [{ ...first, more_files: 1 }] };
    expect(text(one)).toContain("and 1 more file");
    expect(text(one)).not.toContain("1 more files");
  });

  test("says a hotlist kept as written, and shows nothing of one it does not have", () => {
    const kept: AlertView = {
      ...EXPLAINED,
      hotlist: { identifier: "ref-A1", kept_as_written: true, review_date: "2027-01-31" },
    };
    expect(text(kept)).toContain("Hotlist: ref-A1 (kept as written) · review by 31 Jan 2027");
    const none: AlertView = { ...EXPLAINED, hotlist: undefined };
    expect(text(none)).not.toContain("Hotlist:");
  });

  test("an alert whose evidence is withdrawn names nothing of what matched", () => {
    const gone: AlertView = {
      ...EXPLAINED, referent_node_ids: [], evidence_available: false, fired_on: undefined,
    };  // prettier-ignore
    const t = text(gone);
    expect(t).toContain("Evidence no longer available.");
    expect(t).not.toContain("Matched:");
    expect(t).not.toContain("From:");
  });
});
