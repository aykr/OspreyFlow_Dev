// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { StatusBadge } from "./StatusBadge";

afterEach(() => {
  cleanup();
});

describe("test_a_stopped_hotlist_is_visibly_stopped_not_only_flagged_in_data", () => {
  test("a stopped status renders a distinct, visible 'Stopped' label", () => {
    // ADR-036's own binding requirement reaching the render layer, not only the API layer
    // Stage 6c's backend already proved (`Hotlist.status`/`Monitor.status` written on every
    // evaluation attempt): "surfaced as stopped somewhere the analyst... can see it." Asserting
    // on rendered text, not the `status` prop passed in — passing the prop correctly is not the
    // same claim as the label actually reaching the DOM.
    const { container } = render(<StatusBadge status="stopped" />);
    expect(container.textContent).toBe("Stopped");
  });

  test("an active status renders a distinct 'Active' label, not the same text as stopped", () => {
    // Proves the test above is load-bearing: a `StatusBadge` that always rendered a fixed
    // "Stopped" string regardless of `status` would still pass the first test alone. This one
    // fails that regression, since it requires the two states to render differently.
    const { container } = render(<StatusBadge status="active" />);
    expect(container.textContent).toBe("Active");
    expect(container.textContent).not.toBe("Stopped");
  });
});

// ADR-044 Amendment 1: a stopped hotlist or watch says why, beside the label, in the Conduit's words.
describe("a stopped watch says why", () => {
  const WHY = "Its owner can no longer sign in to OspreyFlow.";

  test("the reason is shown beside Stopped", () => {
    const { container } = render(<StatusBadge status="stopped" why={WHY} />);
    expect(container.textContent).toBe(`Stopped${WHY}`);
  });

  test("an active watch shows no reason, even one left behind", () => {
    const { container } = render(<StatusBadge status="active" why={WHY} />);
    expect(container.textContent).toBe("Active");
  });

  test("a stopped watch with no reason still says Stopped", () => {
    const { container } = render(<StatusBadge status="stopped" why={null} />);
    expect(container.textContent).toBe("Stopped");
  });
});

// ADR-044 Amendment 2: an active watch whose last loads could not check its owner's sign-in says so beside Active,
// in the Conduit's words (`status_note`), until the third stops it; a stopped one shows its reason, never the note.
describe("an active watch with unreachable loads says so", () => {
  const NOTE = "Its owner's sign-in could not be checked at the last load. It stops if that happens at three loads in a row.";

  test("the note is shown beside Active", () => {
    const { container } = render(<StatusBadge status="active" note={NOTE} />);
    expect(container.textContent).toBe(`Active${NOTE}`);
  });

  test("a stopped watch shows its reason, not a note left behind", () => {
    const why = "Its owner's sign-in could not be checked at three loads in a row. It is tried again at the next.";
    const { container } = render(<StatusBadge status="stopped" why={why} note={NOTE} />);
    expect(container.textContent).toBe(`Stopped${why}`);
  });

  test("an active watch with no note is Active alone", () => {
    const { container } = render(<StatusBadge status="active" note={null} />);
    expect(container.textContent).toBe("Active");
  });
});
