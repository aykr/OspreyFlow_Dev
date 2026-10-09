// @vitest-environment jsdom
//
// ADR-104 (9 October 2026): a structured transform fills a property through one named part. Map
// offers each part as its own choice, so a binding can never name `person_name` bare, which the
// recipe rules refuse on save.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { FieldBindingEditor } from "./FieldBindingEditor";

afterEach(cleanup);

const TRANSFORMS = [
  { name: "msisdn", arity: 1, parts: [] },
  { name: "person_name", arity: 1, parts: ["family", "given"] },
];

it("offers each part of a structured transform, and not the bare transform", () => {
  const onChange = vi.fn();
  render(
    <FieldBindingEditor
      binding={{ field: "subscriber_name" }}
      sourceFieldNames={["subscriber_name"]}
      transforms={TRANSFORMS}
      onChange={onChange}
    />,
  );
  const select = screen.getByDisplayValue("No transform") as HTMLSelectElement;
  const options = [...select.options].map((o) => [o.value, o.textContent]);
  expect(options).toContainEqual(["person_name(part=family)", "person_name — family"]);
  expect(options).toContainEqual(["person_name(part=given)", "person_name — given"]);
  expect(options.map(([value]) => value)).not.toContain("person_name");
  expect(options.map(([value]) => value)).toContain("msisdn");

  fireEvent.change(select, { target: { value: "person_name(part=family)" } });
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ transform: "person_name(part=family)" }));
});
