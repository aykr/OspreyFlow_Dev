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

import { AlertRow } from "./AlertInbox";
import type { AlertView } from "./api";

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
        <AlertRow alert={NOTIFY_ALERT} onOpen={() => undefined} />
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
        <AlertRow alert={leaking} onOpen={() => undefined} />
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

// ADR-110 decision 10, Amendment 3: a notice that a scheduled run failed or was refused reads as
// its words — not as a match whose evidence vanished, and with no alert to open.
describe("a schedule notice", () => {
  const NOTICE: AlertView = {
    id: "n1", rule_id: "schedule:recipe-1", owner_id: "approver-1", mode: "full", referent_node_ids: [],
    evidence_available: true, investigation_id: "case-1", created_at: "2026-06-02T05:00:00Z",
    words: "The scheduled run of Daily export due 2 June 2026 at 06:00 was refused: the owner can no longer sign in",
  };  // prettier-ignore

  test("reads as its words, with no evidence line and nothing to open", () => {
    const { container, queryByRole } = render(
      <ul>
        <AlertRow alert={NOTICE} onOpen={() => undefined} />
      </ul>,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Scheduled run");
    expect(text).toContain("was refused: the owner can no longer sign in");
    expect(text).not.toContain("Evidence no longer available");
    expect(queryByRole("button", { name: /Open the alert/ })).toBeNull();
  });
});

// ADR-130 decision 1: a hotlist alert explains itself in the words the owner knows, and shows
// neither the raw rule id nor a node id.
describe("a hotlist alert that explains itself", () => {
  const EXPLAINED: AlertView = {
    id: "alert-9", rule_id: "hotlist:01HZX3Q9K2M5N7P8R0S1T2V3W4", owner_id: "analyst-1", mode: "full",
    referent_node_ids: ["01HZX3Q9K2M5N7P8R0S1T2V3W5"], evidence_available: true,
    investigation_id: "case-1", created_at: "2026-10-02T09:00:00Z",
    hotlist: { identifier: "07700 900918", kept_as_written: false, review_date: "2027-01-31" },
    fired_on: [
      {
        type: "Endpoint", label: "+447700900918", more_files: 0,
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
        <AlertRow alert={alert} onOpen={() => undefined} />
      </ul>,
    );
    return container.textContent ?? "";
  }

  test("reads the hotlist, what matched and where it was read from", () => {
    const t = text(EXPLAINED);
    expect(t).toContain("Hotlist: 07700 900918 · review by 31 Jan 2027");
    expect(t).toContain("Matched: Endpoint +447700900918");
    expect(t).toContain("From: pid_seized_comms_batch2.csv, row 4; pid_pin_calls.csv, 2,013 rows");
  });

  test("shows neither the raw rule id nor a node id, and keeps Open the alert", () => {
    const { container, getByRole } = render(
      <ul>
        <AlertRow alert={EXPLAINED} onOpen={() => undefined} />
      </ul>,
    );
    const t = container.textContent ?? "";
    expect(t).not.toContain("hotlist:");
    expect(t).not.toContain("01HZX3Q9K2M5N7P8R0S1T2V3W");
    expect(getByRole("button", { name: "Open the alert" })).toBeTruthy();
  });

  test("says how many more files, never cutting silently", () => {
    const more: AlertView = {
      ...EXPLAINED,
      fired_on: [{ type: "Endpoint", label: "+447700900918", more_files: 3,
                   files: [{ name: "a.csv", row: 1 }] }],
    };  // prettier-ignore
    expect(text(more)).toContain("From: a.csv, row 2; and 3 more files");
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

// ADR-130 Amendment 1: a node the reader cannot read through the case's datasets is named by type
// and label alone; a file counted by records says so; evidence that went between two reads says so.
describe("the hotlist alert's fired-on text", () => {
  const FULL: AlertView = {
    ...NOTIFY_ALERT,
    mode: "full",
    referent_node_ids: ["n1"],
    evidence_available: true,
  };

  test("withheld sources are said in words, with no file", () => {
    const { container } = render(
      <ul>
        <AlertRow
          alert={{
            ...FULL,
            fired_on: [
              { type: "Endpoint", label: "+447700900918", files: [], more_files: 0, sources_withheld: true },
            ],
          }}
          onOpen={() => undefined}
        />
      </ul>,
    );
    const text = container.textContent ?? "";
    expect(text).toContain(
      "Matched: Endpoint +447700900918 \u2014 its sources are in data this case does not read",
    );
    expect(text).not.toContain("From:");
  });

  test("a file counted by records reads as records, and by rows as rows", () => {
    const { container } = render(
      <ul>
        <AlertRow
          alert={{
            ...FULL,
            fired_on: [
              {
                type: "Endpoint",
                label: "x",
                files: [
                  { name: "a.csv", records: 4 },
                  { name: "b.csv", rows: 2 },
                  { name: "c.csv", row: 3 },
                ],
                more_files: 0,
              },
            ],
          }}
          onOpen={() => undefined}
        />
      </ul>,
    );
    expect(container.textContent ?? "").toContain("a.csv, 4 records; b.csv, 2 rows; c.csv, row 4");
  });

  test("evidence available but nothing fired on says it is no longer available and disables Open the alert", () => {
    const { container, getByRole } = render(
      <ul>
        <AlertRow alert={{ ...FULL, fired_on: null }} onOpen={() => undefined} />
      </ul>,
    );
    expect(container.textContent ?? "").toContain("Evidence no longer available");
    expect((getByRole("button", { name: "Open the alert" }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("an available alert with something fired on keeps Open the alert enabled", () => {
    const { getByRole } = render(
      <ul>
        <AlertRow
          alert={{ ...FULL, fired_on: [{ type: "Endpoint", label: "x", files: [], more_files: 0 }] }}
          onOpen={() => undefined}
        />
      </ul>,
    );
    expect((getByRole("button", { name: "Open the alert" }) as HTMLButtonElement).disabled).toBe(false);
  });
});


describe("when an alert was raised", () => {
  test("is said in British English, day before month, whatever the browser's own locale", () => {
    // Found capturing the guide's Watches screen (step 7b): "10/31/2026, 2:31:52 PM".
    const { container } = render(
      <ul>
        <AlertRow alert={{ ...NOTIFY_ALERT, created_at: "2026-10-31T14:31:52Z" }} onOpen={() => undefined} />
      </ul>,
    );
    expect(container.textContent).toContain("31 Oct 2026, 14:31");
  });
});
