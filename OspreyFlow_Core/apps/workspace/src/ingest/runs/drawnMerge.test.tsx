// @vitest-environment jsdom
// ADR-143 Amendment 2 decision 6 (L3.9): the Studio's *Merge into a dataset…*. What would fail if each
// part were wrong: the panel drawn for a dataset that is not a drawing (or a reader who may not merge
// it); Merge offered before the dry run, or kept after a change the dry run did not see; a match not
// ticked sent anyway, or one ticked not sent; a type the target lacks not said why; a drawing merged
// already offered again; a drawn type mapped onto another of the target's types (Amendment 7) not sent
// as chosen, with each property's place, or a change of mapping kept past the dry run.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DrawnMerge } from "./drawnMerge";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Routes = Record<string, (init?: RequestInit, url?: URL) => { status: number; body: unknown }>;

function serve(routes: Routes) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    // The sheet's chosen mapping (`&mapping=`) is given to its handler, not keyed.
    const parsed = new URL(url);
    parsed.searchParams.delete("mapping");
    const key = `${init?.method ?? "GET"} ${parsed.pathname}${parsed.search}`;
    const hit = routes[key] ?? (() => ({ status: 404, body: { error: "not_found" } }));
    const { status, body } = hit(init, new URL(url));
    return new Response(JSON.stringify(body), { status });
  });
  return calls;
}

const TARGETS = {
  drawn_dataset_id: "d1", drawn_name: "Night visits",
  targets: [{ dataset_id: "src", name: "Prison intel", highest_marking: "OFFICIAL-SENSITIVE", policy: "author_promotes" }],
};  // prettier-ignore
const ITEM = (id: string, label: string, problems: string[] = []) => ({
  item_id: id, element_id: `e-${id}`, kind: "node", type: "Person", label, marking: "OFFICIAL", follows: false,
  source: null, target: null, problems,
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
  // As the Conduit: a type mapped onto none is said at Map and left out by the merge, not a problem
  // of its items (Amendment 7), so it may still be mapped and ticked.
  items: [ITEM("i1", "Mercer"), ITEM("i2", "Tall"), ITEM("i3", "Boat")],
  checks: [{ name: "types", passed: true, words: "Every type in Prison intel's model" }],
  recorded_as: "One load into Prison intel (trigger drawn_merge).",
};  // prettier-ignore
const DRY = {
  target_dataset_id: "src", nodes: 2, links: 0, matches: 1, recorded_as: "",
  left_out: [{ item_id: "i3", label: "Boat", why: "Its type, Vessel, goes into no type of Prison intel (Map): it stays on the drawing, read-only." }],
};  // prettier-ignore
const SENT = {
  id: "m1", load_id: "promotion-9", trigger: "drawn_merge", dataset_id: "src", dataset_name: "Prison intel", case_id: "h",
  case_name: "Night visits", board_id: null, proposed_by: "dana", proposed_by_name: "Dana", proposed_at: "2026-11-09T09:00:00Z",
  status: "committed", nodes: 2, links: 0, left_out: [], may_review: false, why_not: null, revert_command: null,
};  // prettier-ignore

function show() {
  render(<DrawnMerge apiBaseUrl="http://api" bearerToken="t" datasetId="d1" />);
}

describe("Merge into a dataset…", () => {
  it("is not drawn for a dataset that is not a drawing, or a reader who may not merge it", async () => {
    const calls = serve({ "GET /v1/datasets/d1/merge-targets": () => ({ status: 409, body: { error: "not_drawn", detail: "Only a drawn dataset…" } }) });
    show();
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText("Merge into a dataset…")).toBeNull();
  });

  it("maps, matches, runs the dry run first, and merges what the dry run showed", async () => {
    // As the server: once merged, the Studio's gate no longer reaches the drawing (404).
    let merged = false;
    const calls = serve({
      "GET /v1/datasets/d1/merge-targets": () => (merged ? { status: 404, body: { error: "not_found" } } : { status: 200, body: TARGETS }),
      "GET /v1/datasets/d1/merge-sheet?target=src": () => ({ status: 200, body: SHEET }),
      "POST /v1/datasets/d1/merges/dry-run": () => ({ status: 200, body: DRY }),
      "POST /v1/datasets/d1/merges": () => {
        merged = true;
        return { status: 201, body: SENT };
      },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
    fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
    // 1: a type the target lacks says why.
    expect(await screen.findByText("Vessel is not a type of Prison intel's model.")).toBeTruthy();
    // 4 waits for 3.
    const merge = screen.getByRole("button", { name: "4. Merge" }) as HTMLButtonElement;
    expect(merge.disabled).toBe(true);
    // 2: the match, ticked.
    fireEvent.click(screen.getByLabelText(/Mercer looks like Mercer/));
    fireEvent.click(screen.getByRole("button", { name: "Dry run" }));
    expect(await screen.findByText(/It would add 2 items and 0 links to Prison intel, and propose 1 match/)).toBeTruthy();
    expect(merge.disabled).toBe(false);
    // A change after the dry run asks for it again.
    fireEvent.click(screen.getByLabelText(/Mercer looks like Mercer/));
    expect(merge.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Mercer looks like Mercer/));
    fireEvent.click(screen.getByRole("button", { name: "Dry run" }));
    await waitFor(() => expect(merge.disabled).toBe(false));
    fireEvent.click(merge);
    expect(await screen.findByText("Merge sent")).toBeTruthy();
    expect(screen.getByText(/load promotion-9/)).toBeTruthy();
    const sent = calls.filter((c) => c.url.endsWith("/merges")).map((c) => JSON.parse(String(c.init?.body)));
    expect(sent).toEqual([
      {
        target_dataset_id: "src",
        item_ids: ["i1", "i2", "i3"],
        matches: [{ drawn: "e-i1", loaded: "p-loaded" }],
        mapping: [
          { kind: "node", drawn_type: "Person", target_type: "Person", properties: [] },
          { kind: "node", drawn_type: "Vessel", target_type: null, properties: [] },
        ],
      },
    ]);
  });

  it("maps a drawn type onto another of the target's types, each property placed, and sends it as chosen", async () => {
    // As the Conduit: under a mapping of Vessel onto Organisation, the boat is looked for as one.
    const BOAT = { drawn: "e-i3", drawn_label: "Boat", loaded: "o-boat", loaded_label: "Boat Ltd", loaded_type: "Organisation", score: 0.9, why: "a name alike" };
    const calls = serve({
      "GET /v1/datasets/d1/merge-targets": () => ({ status: 200, body: TARGETS }),
      "GET /v1/datasets/d1/merge-sheet?target=src": (_init, url) => {
        const mapping = JSON.parse(url?.searchParams.get("mapping") ?? "[]") as { drawn_type: string; target_type: string | null }[];
        const vessel = mapping.find((m) => m.drawn_type === "Vessel")?.target_type ?? null;
        return { status: 200, body: vessel === "Organisation" ? { ...SHEET, matches: [...SHEET.matches, BOAT] } : SHEET };
      },
      "POST /v1/datasets/d1/merges/dry-run": () => ({ status: 200, body: { ...DRY, nodes: 3, retyped: 1, left_out: [] } }),
      "POST /v1/datasets/d1/merges": () => ({ status: 201, body: SENT }),
    });
    show();
    fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
    fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
    const vessel = (await screen.findByLabelText("Vessel goes in as")) as HTMLSelectElement;
    expect(vessel.value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Dry run" }));
    const merge = screen.getByRole("button", { name: "4. Merge" }) as HTMLButtonElement;
    await waitFor(() => expect(merge.disabled).toBe(false));
    // A change of mapping after the dry run asks for it again.
    fireEvent.change(vessel, { target: { value: "Organisation" } });
    expect(merge.disabled).toBe(true);
    expect(screen.getByText(/Each goes in as a new Organisation, a new item beside its drawn one/)).toBeTruthy();
    // Match is read again under the mapping: the boat now looks like an Organisation loaded there.
    const boat = (await screen.findByLabelText(/Boat looks like Boat Ltd \(Organisation\)/)) as HTMLInputElement;
    const sheets = calls.filter((c) => c.url.includes("/merge-sheet"));
    expect(JSON.parse(new URL(sheets.at(-1)?.url ?? "http://api").searchParams.get("mapping") ?? "[]")[1]).toEqual({
      kind: "node",
      drawn_type: "Vessel",
      target_type: "Organisation",
      properties: [
        { drawn_property: "flag", target_property: null },
        { drawn_property: "name", target_property: "name" },
      ],
    });
    // Each drawn property: the same name when the type has it, else not carried, until chosen.
    const name = screen.getByLabelText("name goes into") as HTMLSelectElement;
    const flag = screen.getByLabelText("flag goes into") as HTMLSelectElement;
    expect([name.value, flag.value]).toEqual(["name", ""]);
    fireEvent.change(flag, { target: { value: "country" } });
    fireEvent.click(boat);
    fireEvent.click(screen.getByRole("button", { name: "Dry run" }));
    expect(await screen.findByText(/It would add 3 items and 0 links to Prison intel, 1 of them as new items of another type, and propose 1 match\./)).toBeTruthy();
    fireEvent.click(merge);
    expect(await screen.findByText("Merge sent")).toBeTruthy();
    const sent = calls.filter((c) => c.url.endsWith("/merges")).map((c) => JSON.parse(String(c.init?.body)));
    expect(sent[0].matches).toEqual([{ drawn: "e-i3", loaded: "o-boat" }]);
    expect(sent[0].mapping).toEqual([
      { kind: "node", drawn_type: "Person", target_type: "Person", properties: [] },
      {
        kind: "node",
        drawn_type: "Vessel",
        target_type: "Organisation",
        properties: [
          { drawn_property: "flag", target_property: "country" },
          { drawn_property: "name", target_property: "name" },
        ],
      },
    ]);
  });

  it("lets a chosen match go when the mapping no longer offers it", async () => {
    const calls = serve({
      "GET /v1/datasets/d1/merge-targets": () => ({ status: 200, body: TARGETS }),
      // As the Conduit: a Person left out has no matches.
      "GET /v1/datasets/d1/merge-sheet?target=src": (_init, url) => {
        const mapping = JSON.parse(url?.searchParams.get("mapping") ?? "[]") as { drawn_type: string; target_type: string | null }[];
        const out = mapping.find((m) => m.drawn_type === "Person")?.target_type === null;
        return { status: 200, body: out ? { ...SHEET, matches: [] } : SHEET };
      },
      "POST /v1/datasets/d1/merges/dry-run": () => ({ status: 200, body: { ...DRY, nodes: 0, matches: 0 } }),
    });
    show();
    fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
    fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
    fireEvent.click(await screen.findByLabelText(/Mercer looks like Mercer/));
    fireEvent.change(screen.getByLabelText("Person goes in as"), { target: { value: "" } });
    await waitFor(() => expect(screen.queryByLabelText(/Mercer looks like Mercer/)).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Dry run" }));
    await screen.findByRole("status");
    const dry = calls.filter((c) => c.url.endsWith("/dry-run")).map((c) => JSON.parse(String(c.init?.body)));
    expect(dry[0].matches).toEqual([]);
  });

  it("drops a Match reply that arrives after a newer one", async () => {
    // As a slow network: the first re-read (Vessel onto Organisation) answers after the second
    // (Vessel left out again), and must not overwrite it.
    const BOAT = { drawn: "e-i3", drawn_label: "Boat", loaded: "o-boat", loaded_label: "Boat Ltd", loaded_type: "Organisation", score: 0.9, why: "a name alike" };
    let release: () => void = () => undefined;
    const slow = new Promise<void>((done) => {
      release = done;
    });
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      calls.push(url);
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/merge-targets")) return new Response(JSON.stringify(TARGETS), { status: 200 });
      const mapping = JSON.parse(parsed.searchParams.get("mapping") ?? "[]") as { drawn_type: string; target_type: string | null }[];
      const vessel = mapping.find((m) => m.drawn_type === "Vessel")?.target_type ?? null;
      if (vessel === "Organisation") {
        await slow;
        return new Response(JSON.stringify({ ...SHEET, matches: [...SHEET.matches, BOAT] }), { status: 200 });
      }
      return new Response(JSON.stringify(SHEET), { status: 200 });
    });
    show();
    fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
    fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
    const vessel = (await screen.findByLabelText("Vessel goes in as")) as HTMLSelectElement;
    fireEvent.change(vessel, { target: { value: "Organisation" } });
    fireEvent.change(vessel, { target: { value: "" } });
    await waitFor(() => expect(calls.filter((c) => c.includes("/merge-sheet")).length).toBe(3));
    release();
    await new Promise((done) => setTimeout(done, 20));
    expect(screen.queryByLabelText(/Boat looks like Boat Ltd/)).toBeNull();
  });

  it("shows a refusal in the Conduit's words", async () => {
    serve({
      "GET /v1/datasets/d1/merge-targets": () => ({ status: 200, body: TARGETS }),
      "GET /v1/datasets/d1/merge-sheet?target=src": () => ({ status: 404, body: { error: "not_a_target", detail: "No dataset of that id may take this drawing from you." } }),
    });
    show();
    fireEvent.change(await screen.findByLabelText("Merge into"), { target: { value: "src" } });
    fireEvent.click(screen.getByRole("button", { name: "Map and match" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("No dataset of that id may take this drawing from you.")).toBeTruthy();
  });
});
