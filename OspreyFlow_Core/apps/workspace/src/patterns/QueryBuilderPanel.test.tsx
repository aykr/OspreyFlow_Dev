// @vitest-environment jsdom
// ADR-096: the Query builder opens on its preview, the pattern with Preview and Run, and folds the
// rest; Connect appears once there are two nodes to connect.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema } from "../../../../packages/schemas/generated";
import { QueryBuilderPanel } from "./QueryBuilderPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCHEMA = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] }],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"] }],
} as unknown as OntologySchema;

function mount() {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ patterns: [] }) })));
  render(<QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={SCHEMA} />);
}

const header = (name: string) => screen.getByRole("button", { name });

describe("QueryBuilderPanel parts", () => {
  it("opens on the pattern, with Preview and Run, and folds adding, saving and loading", () => {
    mount();
    expect(header("Pattern").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: "Preview" })).toBeTruthy();
    expect(screen.getByText(/No pattern yet/)).toBeTruthy();
    expect(header("Add to the pattern").getAttribute("aria-expanded")).toBe("false");
    expect(header("Save and load").getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "Add variable" })).toBeNull(); // hidden while folded
    expect(screen.queryByRole("button", { name: "Connect" })).toBeNull();
  });

  it("opening Add to the pattern offers Add variable, and two nodes bring Connect", () => {
    mount();
    fireEvent.click(header("Add to the pattern"));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(screen.getAllByRole("group", { name: /^Pattern node/ })).toHaveLength(2);
    expect(header("Connect").getAttribute("aria-expanded")).toBe("false");
  });
});

// ADR-121: a value field on a node, offered the type's indexed text properties only.
const CONDITION_SCHEMA = {
  version: 1,
  entity_types: [
    {
      name: "Establishment",
      pole_class: "place",
      channel: "teal",
      shape: "square",
      identifiers: [],
      properties: [
        { name: "niu_area", type: "string", indexed: true },
        { name: "soct_region", type: "string", indexed: true },
        { name: "wing", type: "string", indexed: true },
        { name: "block", type: "string", indexed: true },
        { name: "secret_code", type: "string", indexed: true, sensitivity: "high" },
        { name: "note", type: "string" },
      ],
    },
  ],
  edge_types: [],
} as unknown as OntologySchema;

function mountWithConditions() {
  const fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    void init;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => (String(url).endsWith("/preview") ? { estimated_count: 3, is_floor: false } : { patterns: [] }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={CONDITION_SCHEMA} />,
  );
  fireEvent.click(header("Add to the pattern"));
  fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
  return fetchMock;
}

describe("QueryBuilderPanel value field on a node", () => {
  it("offers only the indexed, non-sensitive text properties of the node's type", () => {
    mountWithConditions();
    const property = screen.getByRole("combobox", { name: "Condition property on a" }) as HTMLSelectElement;
    expect(Array.from(property.options).map((o) => o.value)).toEqual(["niu_area", "soct_region", "wing", "block"]);
  });

  it("adds a condition, shows it, and sends it in the preview as PatternNode.where", async () => {
    const fetchMock = mountWithConditions();
    fireEvent.change(screen.getByRole("combobox", { name: "Condition property on a" }), {
      target: { value: "niu_area" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    expect(screen.getByText("niu_area = North")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText("~3 matches");
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/patterns/preview"));
    const body = JSON.parse(call?.[1]?.body ?? "{}");
    expect(body.nodes[0].where).toEqual({ niu_area: "North" });
  });

  it("removes a condition by its own button", () => {
    mountWithConditions();
    fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove condition niu_area on a" }));
    expect(screen.queryByText("niu_area = North")).toBeNull();
  });

  it("stops offering the field at three conditions", () => {
    mountWithConditions();
    for (const [name, value] of [["niu_area", "A"], ["soct_region", "B"], ["wing", "C"]] as const) {
      fireEvent.change(screen.getByRole("combobox", { name: "Condition property on a" }), { target: { value: name } });
      fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    }
    expect(screen.getAllByText(/ = /)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Add condition on a" })).toBeNull();
  });

  it("typing in the value field is not Delete on the node: Backspace keeps the node", () => {
    mountWithConditions();
    const value = screen.getByRole("textbox", { name: "Condition value on a" });
    fireEvent.keyDown(value, { key: "Backspace" });
    expect(screen.getAllByRole("group", { name: /^Pattern node/ })).toHaveLength(1);
  });

  it("offers no field for a type with nothing to match on", () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ patterns: [] }) })));
    render(<QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={SCHEMA} />);
    fireEvent.click(header("Add to the pattern"));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(screen.queryByRole("combobox", { name: "Condition property on a" })).toBeNull();
  });
});

// ADR-129 decision 2: an Ask to search box above the pattern. The proposed pattern is drawn in the
// builder with its explanation and count, nothing runs, and Run is the existing route.
const ASK_SCHEMA = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] }],
  edge_types: [{ name: "VISITED", from: ["Person"], to: ["Person"], directed: true }],
} as unknown as OntologySchema;

const PROPOSAL = {
  pattern: {
    nodes: [
      { var: "a", entity_type: "Person", node_id: null },
      { var: "b", entity_type: "Person", node_id: "n-dana" },
    ],
    edges: [{ edge_type: "VISITED", from_var: "a", to_var: "b" }],
    limit: 1000,
  },
  explanation: "Finds people who visited the selected person.",
  estimated_count: 4,
  is_floor: false,
};

function mountAsk(ask: { ok: boolean; status: number; body: unknown }, selected: string[] = ["n-dana"]) {
  const fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    void init;
    const target = String(url);
    if (target.endsWith("/patterns/ask")) {
      return Promise.resolve({ ok: ask.ok, status: ask.status, json: async () => ask.body });
    }
    if (target.endsWith("/patterns/run")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ mode: "sync", subgraph: { nodes: [], edges: [] }, matched_count: 4 }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ patterns: [] }) });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryBuilderPanel
      investigationId="inv-1"
      apiBaseUrl="http://api.test"
      bearerToken="tok"
      schema={ASK_SCHEMA}
      selectedNodeIds={selected}
    />,
  );
  return fetchMock;
}

const asked = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/patterns/ask"));

describe("QueryBuilderPanel ask to search", () => {
  it("offers a question box and an Ask button that waits for a question", () => {
    mountAsk({ ok: true, status: 200, body: PROPOSAL });
    expect(screen.getByRole("textbox", { name: "Ask to search" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: "  " } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("draws the proposed pattern with its explanation and count, sending the selection and running nothing", async () => {
    const fetchMock = mountAsk({ ok: true, status: 200, body: PROPOSAL });
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), {
      target: { value: "Who visited the principal?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText(/Finds people who visited the selected person\./);
    expect(screen.getByRole("group", { name: "Pattern node a: Person" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Pattern node b: Person · n-dana" })).toBeTruthy();
    expect(screen.getByText("~4 matches")).toBeTruthy();
    expect(screen.getByText(/Check the pattern before you run it/)).toBeTruthy();

    const [, init] = asked(fetchMock)[0] as [string, { body: string }];
    expect(JSON.parse(init.body)).toEqual({
      question: "Who visited the principal?",
      selected_node_ids: ["n-dana"],
    });
    const runs = fetchMock.mock.calls.filter(([url]) => /\/patterns\/(run|preview)$/.test(String(url)));
    expect(runs).toHaveLength(0); // nothing ran, and the count is the one the proposal came with
  });

  it("runs the proposed pattern only when Run is pressed, through the existing run route", async () => {
    const fetchMock = mountAsk({ ok: true, status: 200, body: PROPOSAL });
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("~4 matches");

    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("4 node(s) matched.");
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/patterns/run")) as [
      string,
      { body: string },
    ];
    const sent = JSON.parse(init.body);
    expect(sent.nodes.map((n: { var: string; node_id: string | null }) => [n.var, n.node_id])).toEqual([
      ["a", null],
      ["b", "n-dana"],
    ]);
    expect(sent.edges).toEqual([{ edge_type: "VISITED", from_var: "a", to_var: "b" }]);
  });

  it("asks on Enter in the box as well", async () => {
    const fetchMock = mountAsk({ ok: true, status: 200, body: PROPOSAL });
    const box = screen.getByRole("textbox", { name: "Ask to search" });
    fireEvent.change(box, { target: { value: "q" } });
    fireEvent.keyDown(box, { key: "Enter" });
    await screen.findByText("~4 matches");
    expect(asked(fetchMock)).toHaveLength(1);
  });

  it("says it could not express the question and draws nothing", async () => {
    mountAsk({
      ok: false,
      status: 422,
      body: { error: "could_not_express", reason: "model_declined", detail: "The question cannot be put in this case's vocabulary." },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: "Who is guilty?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/Could not express the question as a pattern\./);
    expect(screen.queryAllByRole("group", { name: /^Pattern node/ })).toHaveLength(0);
    expect(screen.queryByText(/matches/)).toBeNull();
  });

  it("an edit to the proposed pattern clears the count and the explanation, which no longer describe it", async () => {
    mountAsk({ ok: true, status: 200, body: PROPOSAL });
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("~4 matches");

    fireEvent.keyDown(screen.getByRole("group", { name: "Pattern node a: Person" }), { key: "Delete" });
    expect(screen.queryByText("~4 matches")).toBeNull();
    expect(screen.queryByText(/Finds people who visited/)).toBeNull();
  });

  it("sends no selection when nothing is selected", async () => {
    const fetchMock = mountAsk({ ok: true, status: 200, body: PROPOSAL }, []);
    fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("~4 matches");
    const [, init] = asked(fetchMock)[0] as [string, { body: string }];
    expect(JSON.parse(init.body).selected_node_ids).toEqual([]);
  });
});

// ADR-129 decision 2, as a way of starting over: a proposal is a new, unsaved pattern. It must not
// take the saved pattern's identity (Save would overwrite it with the model's), must not discard
// what was drawn without a way back, and must not land on edits made while it was being worked out.
const SAVED = {
  pattern_id: "p1",
  name: "Shared visitors",
  version: 2,
  definition: {
    nodes: [
      { var: "s", entity_type: "Person", node_id: null },
      { var: "t", entity_type: "Person", node_id: "n-rohan" },
    ],
    edges: [{ edge_type: "VISITED", from_var: "s", to_var: "t" }],
    limit: 1000,
  },
};

function mountSaved(delayAsk = false) {
  let release: (() => void) | null = null;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    void init;
    const target = String(url);
    const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
    if (target.endsWith("/patterns/ask")) {
      if (!delayAsk) return ok(PROPOSAL);
      return new Promise((resolve) => {
        release = () => resolve({ ok: true, status: 200, json: async () => PROPOSAL });
      });
    }
    if (target.endsWith("/patterns/save")) return ok({ ...SAVED, pattern_id: "new-id", version: 1 });
    if (target.endsWith("/patterns/p1")) return ok(SAVED);
    return ok({ patterns: [SAVED] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={ASK_SCHEMA} />);
  return { fetchMock, release: () => release?.() };
}

async function loadSaved() {
  fireEvent.click(header("Save and load"));
  await screen.findByRole("option", { name: "Shared visitors (v2)" });
  fireEvent.change(screen.getByRole("combobox", { name: "Saved patterns" }), { target: { value: "p1" } });
  fireEvent.click(screen.getByRole("button", { name: "Load" }));
  await screen.findByRole("group", { name: "Pattern node s: Person" });
}

function ask(text = "Who visited the principal?") {
  fireEvent.change(screen.getByRole("textbox", { name: "Ask to search" }), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("QueryBuilderPanel ask to search over a pattern already there", () => {
  it("starts a new unsaved pattern: Save then writes a new one, never a version of the loaded pattern", async () => {
    const { fetchMock } = mountSaved();
    await loadSaved();
    expect(screen.getByRole("button", { name: "Save new version" })).toBeTruthy();
    ask();
    await screen.findByText("~4 matches");
    expect((screen.getByRole("textbox", { name: "Pattern name" }) as HTMLInputElement).value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved as version 1.");
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/patterns/save")) as [string, { body: string }];
    expect(JSON.parse(init.body).pattern_id).toBeNull();
    expect(JSON.parse(init.body).name).not.toBe("Shared visitors");
  });

  it("keeps the replaced pattern, and one press of Restore the previous pattern brings it back with its identity", async () => {
    const { fetchMock } = mountSaved();
    await loadSaved();
    ask();
    await screen.findByText("~4 matches");
    expect(screen.queryByRole("group", { name: "Pattern node s: Person" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Restore the previous pattern" }));
    expect(screen.getByRole("group", { name: "Pattern node s: Person" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Pattern node t: Person · n-rohan" })).toBeTruthy();
    expect(screen.queryByText(/Finds people who visited/)).toBeNull();
    expect((screen.getByRole("textbox", { name: "Pattern name" }) as HTMLInputElement).value).toBe("Shared visitors");
    expect(screen.getByRole("button", { name: "Save new version" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Restore the previous pattern" })).toBeNull();
    void fetchMock;
  });

  it("keeps an unsaved pattern the analyst drew, and restores it", async () => {
    mountSaved();
    fireEvent.click(header("Add to the pattern"));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(screen.getByRole("group", { name: "Pattern node a: Person" })).toBeTruthy();
    ask();
    await screen.findByText("~4 matches");
    fireEvent.click(screen.getByRole("button", { name: "Restore the previous pattern" }));
    expect(screen.getAllByRole("group", { name: /^Pattern node/ })).toHaveLength(1);
    expect(screen.queryByText("~4 matches")).toBeNull();
  });

  it("offers no restore when there was nothing to replace", async () => {
    mountSaved();
    ask();
    await screen.findByText("~4 matches");
    expect(screen.queryByRole("button", { name: "Restore the previous pattern" })).toBeNull();
  });

  it("does not apply a proposal that arrives after the pattern was edited meanwhile, and says so", async () => {
    const { release } = mountSaved(true);
    await loadSaved();
    ask();
    // While the model works, the analyst edits.
    fireEvent.keyDown(screen.getByRole("group", { name: "Pattern node t: Person · n-rohan" }), { key: "Delete" });
    release();
    await screen.findByText(/arrived after you changed the pattern/);
    expect(screen.getByRole("group", { name: "Pattern node s: Person" })).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Pattern node t: Person · n-rohan" })).toBeNull();
    expect(screen.queryByText("~4 matches")).toBeNull();
    expect(screen.queryByRole("button", { name: "Restore the previous pattern" })).toBeNull();
  });
});
