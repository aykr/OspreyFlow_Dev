// @vitest-environment jsdom
// A drawn item's source on the React board (ADR-143 Amendment 8 items 7 and 8; slice GG4b). The keyboard cases are
// `keyboard/boards.spec.ts`. What would fail if it were wrong:
//  - the inspector saying, of an empty note, anything but "No source note was given" (as built it said "None: a document of the
//    case", which tells a reader sent the item without its document that there is one);
//  - the drawing form, the link form or the edit form sending an item with a document and no note, which the Conduit refuses.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { BoardsPlace } from "./BoardsPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Json = Record<string, unknown>;

const AT = "2026-11-08T10:00:00Z";
const GRADE = { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" };
const handling: Json = { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" };
const audit: Json = { created_at: AT, created_by: "alice" };

/** A drawn person as the Conduit sends one: its source the note's own, with whatever note and document `drawn` holds. */
function person(id: string, label: string, drawn: Json): Json {
  return {
    id,
    type: "Person",
    properties: {},
    provenance: {
      state: "asserted",
      sources: [{ document_id: `drawn:i-${id}`, locator: "a drawing board of the case", excerpt_hash: "" }],
      first_seen: AT,
      drawn: { provenance_class: "analyst_drawn", item_id: `i-${id}`, asserted_by: "alice", board_id: "b1", case_id: "k", label, grading: GRADE, ...drawn },
    },
    handling,
    audit,
    datasets: ["layer"],
  };
}

const memo: Json = {
  id: "doc-memo",
  type: "Document",
  properties: { title: "Memo" },
  provenance: { state: "asserted", sources: [{ document_id: "files/memo.txt", locator: "whole", excerpt_hash: "" }], first_seen: AT },
  handling,
  audit,
  datasets: ["src"],
};

const NODES = [
  // Sent with neither: an item drawn before with a document, to a reader who may not read it.
  person("old", "Old lead", { source_note: null, source_document: null }),
  person("blank", "Blank lead", { source_note: "  " }),
  person("noted", "Noted lead", { source_note: "Seen from the quay", source_document: null }),
  // Drawn before with a document and no note, as its author who may still read the document is sent it.
  person("kept", "Kept lead", { source_note: null, source_document: "doc-memo" }),
  memo,
];

async function board(): Promise<{ sent: { method: string; path: string; body: Json }[] }> {
  const sent: { method: string; path: string; body: Json }[] = [];
  const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const path = new URL(String(input)).pathname;
    const method = init.method ?? "GET";
    if (method !== "GET") {
      sent.push({ method, path, body: JSON.parse(String(init.body ?? "{}")) as Json });
      return answer({ element_id: "old", item_id: "i-old" }, method === "POST" ? 201 : 200);
    }
    if (path.endsWith("/boards/b1")) {
      return answer({
        board: { id: "b1", case_id: "k", name: "Wing B", created_by: "alice", created_at: AT, shared: true, drawn: 3, start: "blank" },
        nodes: NODES,
        edges: [],
        drawn: ["old", "blank", "noted", "kept"],
        items: { old: "i-old", blank: "i-blank", noted: "i-noted", kept: "i-kept" },
        layout: {},
        missing: 0,
        node_types: ["Person"],
        link_types: ["ASSOCIATE_OF"],
        markings: ["OFFICIAL"],
        ceiling: "OFFICIAL",
        grading_scheme: "5x5x5",
        grading_grades: { scheme: "5x5x5", source: ["A", "B"], intelligence: ["1", "2"], handling: ["1", "2"] },
        may_draw: true,
        may_promote: false,
      });
    }
    if (path.endsWith("/matches")) return answer({ suggestions: [], more: false });
    if (path.endsWith("/pictures")) return answer({ pictures: {} });
    if (path.endsWith("/promotions")) return answer({ promotions: [] });
    return answer({ detail: "Not here." }, 404);
  });
  render(<BoardsPlace apiBaseUrl="http://conduit.test" bearerToken="t" caseId="k" caseName="Kestrel" selection={[]} entityTypes={[]} markings={["OFFICIAL"]} mayDraw initialBoard="b1" />);
  await screen.findByRole("button", { name: item("Old lead") });
  return { sent };
}

/** A board item's button, by its name: "Person Old lead (drawn)" (jsdom spaces the spans as it likes). */
const item = (label: string): RegExp => new RegExp(`^Person\\s*${label}`);
const select = (label: string) => fireEvent.click(screen.getByRole("button", { name: item(label) }));
const inspector = (label: string) => screen.getByRole("region", { name: label });
const refusal = () => screen.getByRole("alert").textContent ?? "";

test.each(["Old lead", "Blank lead"])("the inspector says no source note was given for %s, and nothing of a document", async (label) => {
  await board();
  select(label);
  const said = inspector(label).textContent ?? "";
  expect(said).toContain("Source noteNo source note was given");
  expect(said).not.toMatch(/document/i);
});

test("the inspector says a note as it is", async () => {
  await board();
  select("Noted lead");
  expect(inspector("Noted lead").textContent).toContain("Source noteSeen from the quay");
});

test("an item is not declared with a document and no note", async () => {
  const { sent } = await board();
  fireEvent.click(screen.getByRole("radio", { name: "Person" }));
  fireEvent.click(screen.getByRole("button", { name: "Declare a Person" }));
  fireEvent.change(screen.getByLabelText("What do you call it?"), { target: { value: "Visitor" } });
  fireEvent.change(screen.getByLabelText("A document of the case (optional)"), { target: { value: "doc-memo" } });
  fireEvent.click(screen.getByRole("button", { name: "Add to board" }));
  expect(refusal()).toContain("Give a source note");
  expect(sent).toEqual([]);

  fireEvent.change(screen.getByLabelText("Source note"), { target: { value: "Gate log" } });
  fireEvent.click(screen.getByRole("button", { name: "Add to board" }));
  await waitFor(() => expect(sent.map((s) => s.path)).toContain("/v1/investigations/k/boards/b1/items"));
  expect(sent[0]!.body).toMatchObject({ source_note: "Gate log", source_document: "doc-memo" });
});

test("a link is not drawn with a document and no note", async () => {
  const { sent } = await board();
  select("Noted lead");
  fireEvent.click(screen.getByRole("button", { name: "Draw a link…" }));
  const form = screen.getByRole("dialog", { name: /New link from Noted lead/ });
  fireEvent.change(within(form).getByLabelText("Links to"), { target: { value: "old" } });
  fireEvent.change(within(form).getByLabelText("A document of the case (optional)"), { target: { value: "doc-memo" } });
  fireEvent.click(within(form).getByRole("button", { name: "Draw the link" }));
  expect(refusal()).toContain("Give a source note");
  expect(sent).toEqual([]);
});

test.each([
  ["Old lead", undefined],
  ["Kept lead", "doc-memo"],
])("%s, drawn before with no note, is not saved until it is given one", async (label, document) => {
  const { sent } = await board();
  select(label);
  fireEvent.click(screen.getByRole("button", { name: `Edit ${label}` }));
  fireEvent.click(screen.getByRole("button", { name: "Save the change" }));
  expect(refusal()).toContain("Give a source note");
  expect(sent).toEqual([]);

  fireEvent.change(screen.getByLabelText("Source note"), { target: { value: "Wing officer, 4 Nov" } });
  fireEvent.click(screen.getByRole("button", { name: "Save the change" }));
  await waitFor(() => expect(sent.map((s) => s.method)).toContain("PATCH"));
  expect(sent[0]!.body).toMatchObject({ source_note: "Wing officer, 4 Nov" });
  // The document is sent only where the item was sent with one: where it was not, what the Conduit holds is left as it is.
  expect(sent[0]!.body["source_document"]).toBe(document);
});
