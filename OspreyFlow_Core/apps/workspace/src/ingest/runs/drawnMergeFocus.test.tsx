// @vitest-environment jsdom
// GG1 (WCAG 3.2.2, On Input): the drawn-merge sheet moves focus onto its heading only when it is first
// drawn and when the merge is sent. Choosing a "goes in as" or "goes into" option, or ticking a match,
// must leave focus where the person put it. What would fail if each part were wrong: the heading taking
// focus after every Match re-read (a keyboard user is taken away from the select they just changed);
// the heading not taking focus when the sheet is drawn, or when "Merge sent" replaces it.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DrawnMerge } from "./drawnMerge";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TARGETS = {
  drawn_dataset_id: "d1", drawn_name: "Night visits",
  targets: [{ dataset_id: "src", name: "Prison intel", highest_marking: "OFFICIAL-SENSITIVE", policy: "author_promotes" }],
};  // prettier-ignore
const ITEM = (id: string, label: string) => ({
  item_id: id, element_id: `e-${id}`, kind: "node", type: "Person", label, marking: "OFFICIAL", follows: false,
  source: null, target: null, problems: [],
});  // prettier-ignore
const SHEET = {
  drawn_dataset_id: "d1", drawn_name: "Night visits", target_dataset_id: "src", target_name: "Prison intel",
  highest_marking: "OFFICIAL-SENSITIVE", policy: "author_promotes",
  mapping: [
    { kind: "node", drawn_type: "Person", target_type: "Person", items: 2, why_not: null, choices: ["Organisation", "Person"], drawn_properties: ["family_name"] },
    { kind: "node", drawn_type: "Vessel", target_type: null, items: 1, why_not: "Vessel is not a type of Prison intel's model.", choices: ["Organisation", "Person"], drawn_properties: ["flag", "name"] },
  ],
  target_types: [
    { kind: "node", name: "Organisation", properties: ["org_ref", "name", "country"], required: [] },
    { kind: "node", name: "Person", properties: ["family_name", "given_names"], required: ["family_name"] },
  ],
  matches: [{ drawn: "e-i1", drawn_label: "Mercer", loaded: "p-loaded", loaded_label: "Mercer", loaded_type: "Person", score: 1, why: "a name alike" }],
  more_matches: false,
  items: [ITEM("i1", "Mercer"), ITEM("i2", "Tall"), ITEM("i3", "Boat")],
  checks: [{ name: "types", passed: true, words: "Every type in Prison intel's model" }],
  recorded_as: "One load into Prison intel (trigger drawn_merge).",
};  // prettier-ignore
const DRY = { target_dataset_id: "src", nodes: 2, links: 0, matches: 0, recorded_as: "", left_out: [] };
const SENT = {
  id: "m1", load_id: "promotion-9", trigger: "drawn_merge", dataset_id: "src", dataset_name: "Prison intel", case_id: "h",
  case_name: "Night visits", board_id: null, proposed_by: "dana", proposed_by_name: "Dana", proposed_at: "2026-11-09T09:00:00Z",
  status: "committed", nodes: 2, links: 0, left_out: [], may_review: false, why_not: null, revert_command: null,
};  // prettier-ignore

/** The Conduit as the merge routes answer it. A Match read under a chosen mapping (`mapping=`) answers
 * with the match's reason changed, so a test can wait until that answer is drawn. */
function serve() {
  let reads = 0;
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const u = new URL(url);
    const method = init?.method ?? "GET";
    const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
    if (u.pathname === "/v1/datasets/d1/merge-targets") return json(200, TARGETS);
    if (u.pathname === "/v1/datasets/d1/merge-sheet") {
      if (!u.searchParams.has("mapping")) return json(200, SHEET);
      reads += 1;
      return json(200, { ...SHEET, matches: [{ ...SHEET.matches[0], why: `a name alike, read again (${reads})` }] });
    }
    if (u.pathname === "/v1/datasets/d1/merges/dry-run" && method === "POST") return json(200, DRY);
    if (u.pathname === "/v1/datasets/d1/merges" && method === "POST") return json(201, SENT);
    return json(404, { error: "not_found" });
  });
}

async function drawSheet(): Promise<void> {
  render(<DrawnMerge apiBaseUrl="http://api" bearerToken="t" datasetId="d1" />);
  fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
  fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
}

const sheetHeading = () => screen.findByRole("heading", { name: "Merge Night visits into Prison intel" });

describe("the drawn-merge sheet's focus (WCAG 3.2.2)", () => {
  it("moves focus onto the heading when the sheet is first drawn", async () => {
    serve();
    await drawSheet();
    const heading = await sheetHeading();
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  it("leaves focus on a 'goes in as' select, and on a 'goes into' select, after the Match read is answered", async () => {
    serve();
    await drawSheet();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Merge Night visits into Prison intel" })));

    const vessel = screen.getByLabelText("Vessel goes in as") as HTMLSelectElement;
    vessel.focus();
    fireEvent.change(vessel, { target: { value: "Organisation" } });
    // The Match read under the new mapping is answered and drawn.
    expect(await screen.findByLabelText(/read again \(1\)/)).toBeTruthy();
    await act(async () => {});
    expect(document.activeElement).toBe(vessel);

    const flag = screen.getByLabelText("flag goes into") as HTMLSelectElement;
    flag.focus();
    fireEvent.change(flag, { target: { value: "country" } });
    expect(await screen.findByLabelText(/read again \(2\)/)).toBeTruthy();
    await act(async () => {});
    expect(document.activeElement).toBe(flag);
  });

  it("leaves focus on a Match box after it is toggled", async () => {
    serve();
    await drawSheet();
    await sheetHeading();
    const vessel = screen.getByLabelText("Vessel goes in as") as HTMLSelectElement;
    fireEvent.change(vessel, { target: { value: "Organisation" } });
    const match = (await screen.findByLabelText(/read again \(1\)/)) as HTMLInputElement;
    match.focus();
    fireEvent.click(match);
    await act(async () => {});
    expect(match.checked).toBe(true);
    expect(document.activeElement).toBe(match);
  });

  it("moves focus onto the heading again when the merge is sent", async () => {
    serve();
    await drawSheet();
    await sheetHeading();
    const dry = screen.getByRole("button", { name: "Dry run" });
    dry.focus();
    fireEvent.click(dry);
    const merge = screen.getByRole("button", { name: "4. Merge" }) as HTMLButtonElement;
    await waitFor(() => expect(merge.disabled).toBe(false));
    merge.focus();
    fireEvent.click(merge);
    const heading = await screen.findByRole("heading", { name: "Merge sent" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});
