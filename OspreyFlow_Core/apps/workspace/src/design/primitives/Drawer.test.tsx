// @vitest-environment jsdom
//
// A drawer takes focus once, when it opens (spec 02 §6). Seen 9 October 2026 in *Record an
// assessment*: after two characters the statement lost focus to the drawer, and the rest of what
// was typed went nowhere. The drawer refocused itself whenever its `onClose` changed, and its
// parent passes a new one on every render, which each keystroke causes.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it } from "vitest";

import { pressEscapeOnAppear } from "../../testing/actOnAppear";
import { Drawer } from "./Drawer";

afterEach(cleanup);

function Form() {
  const [text, setText] = useState("");
  return (
    <Drawer open onClose={() => undefined} title="Record an assessment">
      <input aria-label="Statement" value={text} onChange={(e) => setText(e.target.value)} />
    </Drawer>
  );
}

it("keeps focus in a field while its parent re-renders on each keystroke", () => {
  render(<Form />);
  const field = screen.getByLabelText("Statement") as HTMLInputElement;
  act(() => field.focus());
  for (const typed of ["O", "OK", "OKA", "OKAF"]) {
    fireEvent.change(field, { target: { value: typed } });
    expect(document.activeElement).toBe(field);
  }
  expect(field.value).toBe("OKAF");
});

it("still takes focus when it opens", () => {
  render(<Form />);
  expect(document.activeElement?.getAttribute("role")).toBe("dialog");
});

// The owner, 9 October 2026, on the Questions drawer: "how do I close the questions panel?" —
// Escape worked but nothing visible said so.
it("offers a visible Close button that closes it", () => {
  let closed = 0;
  render(
    <Drawer open onClose={() => closed++} title="Questions">
      <p>body</p>
    </Drawer>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Close Questions" }));
  expect(closed).toBe(1);
});

// Escape is heard from the moment it can be seen: a listener added in a passive effect missed an
// Escape pressed as it appeared on a slow machine (`Popover`, CI keyboard walkthroughs, 20 October 2026).
it("closes on an Escape pressed as soon as it is in the page", async () => {
  let closed = 0;
  await pressEscapeOnAppear(
    <Drawer open onClose={() => (closed += 1)} title="Record an assessment">
      <input aria-label="Statement" />
    </Drawer>,
    "[role='dialog']",
  );
  expect(closed).toBe(1);
});

// ADR-145 Amendment 14 decision 2 (the owner, 13 November 2026: "the Cases panel covers the top
// navigation"): a drawer opens under the workspace's top bar, and so under the GOV.UK header above it,
// never over them; where there is no top bar (a harness, Admin's own frame) it starts at the top as before.
it("opens under the top bar, never over the navigation above it", () => {
  const bar = document.createElement("header");
  bar.className = "top-bar";
  bar.getBoundingClientRect = () => ({ top: 72, bottom: 112, left: 0, right: 1440, width: 1440, height: 40, x: 0, y: 72, toJSON: () => ({}) });
  document.body.append(bar);
  try {
    render(
      <Drawer open onClose={() => undefined} title="Cases">
        <p>body</p>
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Cases" }).style.top).toBe("112px");
  } finally {
    bar.remove();
  }
});

function placed(className: string, bottom: () => number): HTMLElement {
  const el = document.createElement("div");
  el.className = className;
  el.getBoundingClientRect = () => {
    const b = bottom();
    return { top: b - 40, bottom: b, left: 0, right: 1440, width: 1440, height: 40, x: 0, y: b - 40, toJSON: () => ({}) };
  };
  document.body.append(el);
  return el;
}

// ADR-145 Amendment 14 decision 2, after the orchestrator's review: the context row under the top bar carries the
// case switcher and the cross-link at its right end, which a drawer at the top bar's edge still covered.
it("opens under the context row too, under GOV.UK's banner and OspreyFlow's alike", () => {
  for (const banner of ["context-banner", "govuk-notification-banner context-banner--govuk"]) {
    const bar = placed("top-bar", () => 112);
    const row = placed(banner, () => 153);
    try {
      render(
        <Drawer open onClose={() => undefined} title="Cases">
          <p>body</p>
        </Drawer>,
      );
      expect(screen.getByRole("dialog", { name: "Cases" }).style.top).toBe("153px");
    } finally {
      cleanup();
      bar.remove();
      row.remove();
    }
  }
});

it("is measured again when the window is resized and when the page scrolls", () => {
  let bottom = 112;
  const bar = placed("top-bar", () => bottom);
  try {
    render(
      <Drawer open onClose={() => undefined} title="Cases">
        <p>body</p>
      </Drawer>,
    );
    const drawer = screen.getByRole("dialog", { name: "Cases" });
    expect(drawer.style.top).toBe("112px");
    bottom = 152; // the bar wraps at a narrower window
    act(() => void window.dispatchEvent(new Event("resize")));
    expect(drawer.style.top).toBe("152px");
    bottom = 40; // the page scrolled towards the GOV.UK footer
    act(() => void window.dispatchEvent(new Event("scroll")));
    expect(drawer.style.top).toBe("40px");
    bottom = -20; // scrolled past it: never above the window
    act(() => void window.dispatchEvent(new Event("scroll")));
    expect(drawer.style.top).toBe("0px");
  } finally {
    bar.remove();
  }
});

// The drawer neither traps focus nor makes the page behind it inert, and the navigation beside it stays usable
// (decision 2), so it does not tell assistive technology that the rest of the page is inert.
it("is not announced as modal", () => {
  render(
    <Drawer open onClose={() => undefined} title="Cases">
      <p>body</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Cases" }).getAttribute("aria-modal")).toBeNull();
});

it("starts at the top where there is no top bar", () => {
  render(
    <Drawer open onClose={() => undefined} title="Cases">
      <p>body</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Cases" }).style.top).toBe("");
});
