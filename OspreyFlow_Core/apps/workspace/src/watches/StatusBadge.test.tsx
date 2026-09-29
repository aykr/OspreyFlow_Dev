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
