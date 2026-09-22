// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { Tooltip } from "../design/primitives/Tooltip";
import { ReviewFlagChip } from "./ReviewFlagChip";

afterEach(() => {
  cleanup();
});

describe("test_the_review_flag_chip_renders_the_real_reason_text_without_interaction", () => {
  test("the flag reason is present in the DOM without any hover or focus interaction", () => {
    // `02_GLASS_FRONTEND.md` §9.4 / this stage's own instruction: "a judgement flagged for review
    // because its evidence was retracted is worthless if the flag is invisible." A hover-only
    // `Tooltip` would fail a keyboard/screen-reader user exactly this way — this test never
    // dispatches a mouse or focus event, so a regression back to a hover-gated rendering would
    // make it fail.
    const { container } = render(
      <ReviewFlagChip reason="cited node n1 was superseded" />,
    );
    expect(container.textContent ?? "").toContain("cited node n1 was superseded");
    expect(container.textContent ?? "").toContain("Flagged for review");
  });

  test("the regression this proves against: wrapping the reason in this codebase's own hover-only Tooltip removes it from the DOM until hovered", () => {
    // Proves the assertion above is load-bearing, not vacuous: this codebase already has a
    // hover-only primitive (`design/primitives/Tooltip.tsx`) that would have been the "natural"
    // choice for a status chip's own detail — and it fails exactly the standard `ReviewFlagChip`
    // exists to meet, without any interaction simulated.
    const { container } = render(
      <Tooltip text="cited node n1 was superseded">
        <span>Flagged for review</span>
      </Tooltip>,
    );
    expect(container.textContent ?? "").not.toContain("cited node n1 was superseded");
  });
});
