// @vitest-environment jsdom
// *Show as BPMN* (`06_DECISIONS.md` ADR-146 decision 3), drawn from the `.bpmn` the codec really
// writes (`fixtures/visits-to-listed-people.bpmn`, kept equal to `to_bpmn`'s output by
// `tests/rule_standards/test_codec.py`; rule 15). The keyboard walkthrough is
// `keyboard/rule-standards.spec.ts`.
//
// What a mistake would do, and the case that catches it:
// - the drawing made from something other than the file: `it draws the three elements the file names`;
// - a file of another shape drawn as if it were a rule's: `it does not draw a process OspreyFlow does not run`;
// - focus lost on close: `it gives focus back to the button when it closes`.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { readBpmnDrawing } from "./bpmnDrawing";
import BPMN from "./fixtures/visits-to-listed-people.bpmn?raw";
import { ShowAsBpmn } from "./ShowAsBpmn";

afterEach(cleanup);

function plant(after: string, planted: string): string {
  expect(BPMN).toContain(after);
  return BPMN.replace(after, after + planted);
}

describe("readBpmnDrawing", () => {
  it("reads the three elements and the rule's name from the exported file", () => {
    expect(readBpmnDrawing(BPMN)).toEqual({
      rule: "Visits to listed people",
      start: { id: "when", name: "As data loads, after commit" },
      task: { id: "if", name: "If a Person meets the conditions" },
      end: { id: "then", name: "Raise a high alert" },
    });
  });

  it("does not draw a process OspreyFlow does not run", () => {
    expect(
      readBpmnDrawing(
        plant(
          "</bpmn:endEvent>",
          '<bpmn:endEvent id="then_2" name="Another"/>',
        ),
      ),
    ).toBeNull();
    expect(
      readBpmnDrawing(
        BPMN.replace(
          'sourceRef="if" targetRef="then"',
          'sourceRef="when" targetRef="then"',
        ),
      ),
    ).toBeNull();
    expect(readBpmnDrawing("<not xml")).toBeNull();
  });
});

describe("ShowAsBpmn", () => {
  it("draws the three elements the file names, read-only", () => {
    render(<ShowAsBpmn bpmnXml={BPMN} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show as BPMN" }));
    const dialog = screen.getByRole("dialog", {
      name: "Visits to listed people as BPMN 2.0",
    });
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "A BPMN process of three elements: a start event, “As data loads, after commit”, then a business-rule task, “If a Person meets the conditions”, then an end event, “Raise a high alert”.",
    );
    const elements = screen.getByRole("list", {
      name: "The process's elements, in order",
    });
    expect(elements.textContent).toContain(
      "Start event: As data loads, after commit",
    );
    expect(elements.textContent).toContain("End event: Raise a high alert");
    expect(dialog.querySelectorAll("input, select, textarea")).toHaveLength(0);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Close" }),
    );
  });

  it("says so, and draws nothing, for a file that is not a rule's process", () => {
    render(
      <ShowAsBpmn
        bpmnXml={plant(
          "</bpmn:businessRuleTask>",
          '<bpmn:businessRuleTask id="if_2"/>',
        )}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show as BPMN" }));
    expect(screen.getByRole("status").textContent).toContain(
      "not a process OspreyFlow runs",
    );
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("takes Escape for itself, so the editor around it does not act on it too", () => {
    let editorHeard = 0;
    const editor = (e: KeyboardEvent) => {
      if (e.key === "Escape") editorHeard += 1;
    };
    document.addEventListener("keydown", editor);
    try {
      render(<ShowAsBpmn bpmnXml={BPMN} />);
      fireEvent.click(screen.getByRole("button", { name: "Show as BPMN" }));
      fireEvent.keyDown(screen.getByRole("button", { name: "Close" }), {
        key: "Escape",
      });
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(editorHeard).toBe(0);
    } finally {
      document.removeEventListener("keydown", editor);
    }
  });

  it("gives focus back to the button when it closes, by Escape or by Close", () => {
    render(<ShowAsBpmn bpmnXml={BPMN} />);
    const button = screen.getByRole("button", { name: "Show as BPMN" });
    fireEvent.click(button);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(button);
  });
});
