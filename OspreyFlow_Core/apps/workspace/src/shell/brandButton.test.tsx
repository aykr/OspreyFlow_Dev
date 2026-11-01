// @vitest-environment jsdom
// The top bar's brand button (ADR-132 Amendment 4 ruling 5, as the owner answered on 1 November 2026):
// it shows the mark and "Osprey", and is spoken "Osprey, go to Home". WCAG 2.5.3 (label in name): the
// spoken name starts with the visible label, word for word, so a person who says what they see
// ("click Osprey") reaches it. "OspreyFlow, go to Home" began with a different word than the one shown.
// Under GOV.UK the top bar keeps its mark (ruling 5(b)), so the rule and the name are the same there.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand, type Brand } from "../brand/brand";
import { StartBar } from "./StartPage";
import { TopBar } from "./TopBar";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-brand");
});

/** The words a sighted person reads on the button: its text, the mark's svg being hidden. */
function visibleLabel(button: HTMLElement): string {
  return (button.textContent ?? "").replace(/\s+/g, " ").trim();
}

const BARS = {
  "the workspace's top bar": () => (
    <TopBar app="glass" caseSwitcher={null} account={null} onStart={() => undefined} />
  ),
  "the bar outside a case": () => <StartBar account={null} marking={null} onStart={() => undefined} />,
};

describe.each(["ospreyflow", "govuk"] as Brand[])("the brand button under the %s brand", (brand) => {
  it.each(Object.entries(BARS))("in %s is spoken as its visible label, then where it goes", (_, bar) => {
    applyBrand(brand);
    render(bar());
    const button = screen.getByRole("button", { name: /go to Home/ });
    const label = visibleLabel(button);
    const name = button.getAttribute("aria-label") ?? "";
    expect(label).toBe("Osprey");
    // Word for word: the name's first words are the label's, not a longer word that contains it.
    expect(name.split(/[,\s]/)[0]).toBe(label);
    expect(name).toBe("Osprey, go to Home");
  });
});
