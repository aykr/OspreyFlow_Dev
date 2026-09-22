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

const JUMP_RESULT: AlertJumpResult = {
  investigation: {
    id: "inv-branch-1",
    created_at: "2026-09-22T00:00:00Z",
    created_by: "analyst-1",
    owning_unit: "unit-1",
    branched_from: "inv-source-1",
  },
  seeded_count: 3,
  unreadable_count: 2,
};

describe("test_jump_result_never_frames_unreadable_count_as_newly_visible_content", () => {
  test("the jump summary frames unreadable_count as lost access, never as newly found content", () => {
    const { getByTestId } = render(
      <JumpResultSummary result={JUMP_RESULT} onOpen={() => undefined} />,
    );
    const unreadableText = getByTestId("jump-unreadable-summary").textContent ?? "";

    expect(unreadableText).toBe("2 referents no longer accessible to you.");
    // The framing this test exists to pin, scoped to the *unreadable_count* sentence specifically
    // (not the whole summary — "…added to the new investigation" legitimately uses "new" to
    // describe the investigation itself, which really is new; that is not the claim under test):
    // `unreadable_count` can only ever recount referents belonging to an alert this same viewer
    // already had a standing claim to receive (`AlertStore.get_authorized`/`list_authorized`
    // filter `WHERE owner_id = $1`, ADR-041) — re-checked fresh as the viewer's own current
    // principal (`fetch_jumpable_referents`, `watch_routes.py`). Copy implying newly-revealed or
    // newly-found content would misrepresent that guarantee at the render layer even though the
    // server-side number itself is safe; asserted as an explicit negative match against that one
    // sentence, not just an absence noticed by omission.
    expect(unreadableText).not.toMatch(/new|found|discovered|hidden/i);
  });

  test("a copy regression that frames the count as newly-found content fails this test", () => {
    // A minimal stand-in for the same summary with a copy regression — proves the assertion above
    // is real, not a tautology that would pass against any string.
    function Regressed({ result }: { result: AlertJumpResult }) {
      return <p data-testid="jump-unreadable-summary">{result.unreadable_count} new hidden entities found.</p>;
    }
    const { getByTestId } = render(<Regressed result={JUMP_RESULT} />);
    expect(getByTestId("jump-unreadable-summary").textContent ?? "").toMatch(/new|found|hidden/i);
  });
});
