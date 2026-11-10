// Drawing boards keyboard harness (ADR-143 decisions 4 to 7; Amendment 2 decisions 5 and 8): the
// Glass's *Boards* for case c1, which holds Alice's shared board *Wing B* (two loaded people, Mercer
// and Ward, linked, two drawn items and a loaded image Document, the photo of Mercer) and her private
// board *Night shift*; the case has one view, *Visits*, to start a board from. The Conduit is a stand-in
// kept here, so the axe scan of every harness (`a11y/every-harness.spec.ts`) sees the boards filled: it
// answers each reader as the board routes do (only the creator draws; `?as=bob` reads as another
// member). `?board=<id>` opens a board at once; `?press=<button text>` presses a button (or a radio's label) once drawn, for
// the axe scan of a form or a question. What was sent is on `window.__BOARDS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { BoardsPlace } from "../src/boards/BoardsPlace";
import { applyHarnessBrand } from "./brandHarness";

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

declare global {
  interface Window {
    __BOARDS__?: { sent: Sent[]; caseMade: { caseId: string; boardId: string } | null };
  }
}

const params = new URLSearchParams(window.location.search);
const reader = params.get("as") ?? "alice";
const at = "2026-11-08T10:00:00Z";
const GRADE = { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" };
const MARKINGS = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE"];

type Json = Record<string, unknown>;

const provenance = (drawn: Json | null): Json => ({
  state: "asserted",
  sources: [{ document_id: "doc", locator: "here", excerpt_hash: "" }],
  first_seen: at,
  ...(drawn ? { drawn } : {}),
});
const handling = (classification = "OFFICIAL"): Json => ({ classification, handling_code: "P", originator: "u", owning_unit: "u" });
const audit: Json = { created_at: at, created_by: "alice" };

function loaded(id: string, family: string): Json {
  return { id, type: "Person", properties: { family_name: family }, provenance: provenance(null), handling: handling(), audit, datasets: ["src"] };
}

function documentNode(id: string, title: string): Json {
  return { id, type: "Document", properties: { title, media_kind: "image", object_ref: `media/${id}.png` }, provenance: provenance(null), handling: handling(), audit, datasets: ["src"] };
}

function drawnNode(id: string, item: string, label: string, board: string, by = "alice"): Json {
  return {
    id,
    type: "Person",
    properties: { family_name: label },
    provenance: provenance({ provenance_class: "analyst_drawn", item_id: item, asserted_by: by, board_id: board, case_id: "c1", label, grading: GRADE, source_note: "Wing officer report, 4 Nov" }),
    handling: handling(),
    audit,
    datasets: ["layer"],
  };
}

interface HeldBoard {
  id: string;
  name: string;
  created_by: string;
  shared: boolean;
  nodes: Json[];
  edges: Json[];
  items: Record<string, string>;
  layout: Record<string, { x: number; y: number }>;
}

const boards: HeldBoard[] = [
  {
    id: "b-wing",
    name: "Wing B",
    created_by: "alice",
    shared: true,
    nodes: [loaded("p-mercer", "Mercer"), loaded("p-ward", "Ward"), drawnNode("d-tall", "i-tall", "Unknown male “Tall”", "b-wing"), drawnNode("d-ms", "i-ms", "M. Mercer", "b-wing"), documentNode("doc-photo", "Photo of Mercer, 3 Nov"), drawnNode("d-bob", "i-bob", "Bob’s sketch", "b-bob", "bob")],
    edges: [
      { id: "e-loaded", type: "ASSOCIATE_OF", source: "p-mercer", target: "p-ward", provenance: provenance(null), handling: handling(), audit, datasets: ["src"] },
    ],
    items: { "d-tall": "i-tall", "d-ms": "i-ms", "d-bob": "i-bob" },
    layout: { "p-mercer": { x: 0.2, y: 0.3 }, "p-ward": { x: 0.5, y: 0.3 }, "d-tall": { x: 0.3, y: 0.7 }, "d-ms": { x: 0.75, y: 0.6 }, "doc-photo": { x: 0.85, y: 0.2 }, "d-bob": { x: 0.55, y: 0.85 } },
  },
  { id: "b-night", name: "Night shift", created_by: "alice", shared: false, nodes: [], edges: [], items: {}, layout: {} },
];
let decided = false;
let made = 0;
// L3.4: what was promoted from a board here, and the promotions themselves.
const promotedHere = new Set<string>();
const promotions: Json[] = [];

window.__BOARDS__ = { sent: [], caseMade: null };
const json = (status: number, body: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const visible = (b: HeldBoard) => b.shared || b.created_by === reader;
const wire = (b: HeldBoard) => ({
  id: b.id,
  case_id: "c1",
  name: b.name,
  created_by: b.created_by,
  created_at: at,
  shared: b.shared,
  drawn: Object.keys(b.items).length,
  start: "blank",
});
const opened = (b: HeldBoard) => ({
  board: wire(b),
  nodes: b.nodes,
  edges: b.edges,
  drawn: [...Object.keys(b.items), ...b.edges.filter((e) => (e.provenance as Json).drawn).map((e) => e.id as string)],
  items: { ...b.items },
  layout: b.layout,
  missing: 0,
  node_types: ["Location", "Organisation", "Person", "Vehicle"],
  link_types: ["ASSOCIATE_OF", "FAMILY_OF", "PRESENT_AT"],
  markings: MARKINGS,
  ceiling: "OFFICIAL-SENSITIVE",
  grading_scheme: "5x5x5",
  // As the Conduit's opened board since L3.7 (ADR-143 Amendment 6): the scheme's grades, from GRADING_PARTS;
  // the Glass keeps no list of its own, so without them no grade is offered.
  grading_grades: { scheme: "5x5x5", source: ["A", "B", "C", "D", "E"], intelligence: ["1", "2", "3", "4", "5"], handling: ["1", "2", "3", "4", "5"] },
  may_draw: b.created_by === reader,
  // As the Conduit: an Author holding promote_to_dataset; `?promote=no` for a drawer who is neither.
  may_promote: b.created_by === reader && params.get("promote") !== "no",
});

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const url = new URL(String(input));
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = typeof init.body === "string" ? (JSON.parse(init.body) as Json) : init.body ? "(file)" : null;
  window.__BOARDS__!.sent.push({ method, path: path + (url.search || ""), body });
  if (path === "/v1/drawings" && method === "POST") return json(201, { dataset_id: "ds-new", investigation_id: "c-new", board: { ...wire(boards[1]!), id: "b-new", case_id: "c-new" } });
  const base = "/v1/investigations/c1/";
  if (!path.startsWith(base)) return json(404, { error: "not_found" });
  const rest = path.slice(base.length);
  if (rest === "boards" && method === "GET") return json(200, boards.filter(visible).map(wire));
  if (rest === "boards" && method === "POST") {
    // As BoardInput does: a board from a view names the view.
    if ((body as Json).start === "view" && !(body as Json).view_id) return json(422, { detail: [{ loc: ["body"], msg: "a board from a view names the view" }] });
    made += 1;
    const b: HeldBoard = { id: `b-made-${made}`, name: String((body as Json).name), created_by: reader, shared: false, nodes: [], edges: [], items: {}, layout: {} };
    boards.push(b);
    return json(201, wire(b));
  }
  if (rest === "drawn-watches") return json(200, []);
  // The boards' Alerts panel (ADR-146 decision 9): the case's figures and its queue, as the Conduit
  // answers them for this reader (synthetic, rule 9).
  if (rest === "reports" && method === "GET") {
    return json(200, { monitoring: { raised_by_rule: [], closed_by_outcome: [], time_to_close: [], hotlist_matches: [], team: [],
      open_by_source: [{ label: "typology", typology: "structuring", age: "under a day", count: 1 }] } });  // prettier-ignore
  }
  if (rest === "alert-queue" && method === "GET") {
    return json(200, [{ alert: { id: "a1", rule_id: "typology:r", owner_id: "o", mode: "full", referent_node_ids: [], created_at: at, status: "open", typology: "structuring" },
      summary: "Visits to Wing B", kind: "typology" }]);  // prettier-ignore
  }
  if (rest === "views" && method === "GET") {
    return json(200, [{ id: "v-visits", case_id: "c1", name: "Visits", created_by: reader, created_at: at, shared: false, chosen: 2, threshold: 0.9, drawing: false }]);
  }
  const item = /^board-items\/([^/]+)(\/withdraw)?$/.exec(rest);
  if (item) {
    const b = boards.find((x) => Object.values(x.items).includes(item[1]!));
    if (!b) return json(404, { error: "item_not_found" });
    const element = Object.keys(b.items).find((k) => b.items[k] === item[1])!;
    if (item[2]) {
      b.nodes = b.nodes.filter((n) => n.id !== element);
      const gone = b.edges.filter((e) => e.source === element || e.target === element).map((e) => e.id as string);
      b.edges = b.edges.filter((e) => !gone.includes(e.id as string));
      delete b.items[element];
      // As the Conduit answers: every drawn link the reader may see, on this board or another of
      // the case (Tall has one on another board), and its picture apart.
      const elsewhere = element === "d-tall" ? ["e-other-board"] : [];
      return json(200, { nodes: [element], links: [...gone, ...elsewhere], pictures: [], watches_ended: 1 });
    }
    const node = b.nodes.find((n) => n.id === element)!;
    const drawn = (node.provenance as Json).drawn as Json;
    const change = body as Json;
    if (change.label) drawn.label = change.label;
    if (change.grading) drawn.grading = change.grading;
    return json(200, { element_id: element, item_id: item[1] });
  }
  const one = /^boards\/([^/]+)(?:\/(.+))?$/.exec(rest);
  if (!one) return json(404, {});
  const b = boards.find((x) => x.id === one[1] && visible(x));
  if (!b) return json(404, { error: "board_not_found" });
  const tail = one[2] ?? "";
  if (tail === "" && method === "GET") return json(200, opened(b));
  if (tail === "matches" && method === "GET") {
    const ms = b.nodes.find((n) => n.id === "d-ms");
    return json(200, {
      suggestions: !decided && ms ? [{ drawn: "d-ms", loaded: loaded("p-mercer", "Mercer"), score: 0.86, why: "a name alike", state: "inferred" }] : [],
      more: false,
    });
  }
  // `?pictured=1`: Tall has a picture, drawn from a one-pixel png.
  if (tail === "pictures") return json(200, { pictures: params.get("pictured") ? { "d-tall": "doc-photo" } : {} });
  if (/^nodes\/[^/]+\/picture$/.test(tail) && method === "GET") {
    const png = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="), (c) => c.charCodeAt(0));
    return new Response(png, { status: 200, headers: { "Content-Type": "image/png" } });
  }
  // L3.4: the board's own promotions, for a reader who may see it.
  if (tail === "promotions" && method === "GET") return json(200, { promotions: promotions.filter((p) => p.board_id === b.id) });
  if (b.created_by !== reader) return json(403, { error: "not_the_boards_creator", detail: "Only the person who made this board draws on it." });
  if (tail === "promotion-sheet") {
    // As the Conduit's sheet: the drawn items not yet promoted, one failing a check and saying why.
    return json(200, {
      board_id: b.id, dataset_id: "src", dataset_name: "Prison intel", highest_marking: "OFFICIAL-SENSITIVE",
      policy: params.get("policy") ?? "author_promotes",
      items: [
        ...Object.entries(b.items).filter(([id]) => !promotedHere.has(id)).map(([id, itemId]) => {
          const node = b.nodes.find((n) => n.id === id)!;
          const drawn = (node.provenance as Json).drawn as Json;
          return { item_id: itemId, element_id: id, kind: "node", type: node.type, label: drawn.label, marking: "OFFICIAL", follows: false, problems: [] };
        }),
        { item_id: "i-high", element_id: "d-high", kind: "node", type: "Person", label: "Night caller", marking: "SECRET", follows: false,
          problems: ["Marked SECRET, above Prison intel's highest allowed marking, OFFICIAL-SENSITIVE."] },
      ],
      checks: [
        { name: "marking", passed: false, words: "Every marking within Prison intel's highest allowed, OFFICIAL-SENSITIVE: 1 above it" },
        { name: "types", passed: true, words: "Every type in Prison intel's model" },
        { name: "graded", passed: true, words: "Every item graded, with a source" },
        { name: "ends", passed: true, words: "No link without both its ends: a link whose end does not go stays behind" },
      ],
      warnings: decided ? [] : ["M. Mercer looks like a loaded item and has no decision yet: decide Same or Not the same on the board first, or promote it as a separate item."],
      recorded_as: "One load into Prison intel (trigger analyst_promotion), committed at once (the Author promotes).",
    });  // prettier-ignore
  }
  if (tail === "promotions" && method === "POST") {
    const ticked = ((body as Json).item_ids as string[]) ?? [];
    const going = Object.entries(b.items).filter(([, itemId]) => ticked.includes(itemId)).map(([id]) => id);
    going.forEach((id) => promotedHere.add(id));
    const left = Object.entries(b.items).filter(([id, itemId]) => !ticked.includes(itemId) && !promotedHere.has(id))
      .map(([id, itemId]) => ({ item_id: itemId, label: ((b.nodes.find((n) => n.id === id)!.provenance as Json).drawn as Json).label, why: "Not ticked." }));
    const second = params.get("policy") === "second_person_reviews";
    const p = { id: `p-${promotions.length + 1}`, load_id: `promotion-${promotions.length + 1}`, trigger: "analyst_promotion", dataset_id: "src",
      dataset_name: "Prison intel", case_id: "c1", case_name: "Kestrel", board_id: b.id, proposed_by: reader, proposed_by_name: "Alice",
      proposed_at: at, status: second ? "awaiting_review" : "committed", nodes: going.length, links: 0, left_out: left };  // prettier-ignore
    promotions.push(p);
    return json(201, p);
  }
  if (tail === "share") {
    b.shared = true;
    return json(200, wire(b));
  }
  if (tail === "layout") {
    Object.assign(b.layout, (body as Json).positions);
    return json(204, null);
  }
  if (tail === "matches" && method === "POST") {
    decided = true;
    return json(201, { edge_id: "e-decided" });
  }
  if (tail === "items") {
    const given = body as Json;
    if (given.marking === "OFFICIAL-SENSITIVE" && given.label === "Too high") {
      return json(409, { error: "above_the_ceiling", detail: "SECRET is above this case's ceiling, OFFICIAL-SENSITIVE" });
    }
    made += 1;
    const id = `d-made-${made}`;
    b.nodes.push(drawnNode(id, `i-made-${made}`, String(given.label), b.id));
    b.items[id] = `i-made-${made}`;
    b.layout[id] = { x: Number(given.x), y: Number(given.y) };
    return json(201, { element_id: id, item_id: `i-made-${made}`, watch_id: `w-${made}` });
  }
  if (tail === "links") {
    const given = body as Json;
    made += 1;
    b.edges.push({
      id: `e-made-${made}`,
      type: given.type,
      source: given.source,
      target: given.target,
      provenance: provenance({ provenance_class: "analyst_drawn", item_id: `i-link-${made}`, asserted_by: reader, board_id: b.id, case_id: "c1", label: given.label, grading: GRADE, source_note: given.source_note }),
      handling: handling(),
      audit,
      datasets: ["layer"],
    });
    return json(201, { element_id: `e-made-${made}`, item_id: `i-link-${made}`, watch_id: null });
  }
  if (/^nodes\/[^/]+\/picture$/.test(tail) && method === "PUT") {
    // The route requires the picture's own source note (C17 a), as the Conduit's Query does.
    if (!url.searchParams.get("source_note")) return json(422, { detail: [{ loc: ["query", "source_note"], msg: "Field required" }] });
    return json(201, { element_id: "e-picture", item_id: "i-picture" });
  }
  if (/^nodes\/[^/]+\/picture$/.test(tail) && method === "POST") {
    // C17 (b): only an image Document the case holds is a picture.
    const chosen = String((body as Json).document_id);
    const doc = b.nodes.find((n) => n.id === chosen);
    if (!doc || doc.type !== "Document") return json(422, { error: "not_a_picture", detail: "that is not a picture this case holds" });
    return json(201, { element_id: "e-chosen", item_id: "i-chosen" });
  }
  return json(404, {});
};

await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `press` names buttons (or radios, by their label) to press in turn, separated by "|", each once it is drawn.
const presses = (params.get("press") ?? "").split("|").filter(Boolean);
const pressNext = () => {
  const name = presses[0];
  if (!name) return;
  // A button by its text, or a radio by its label's text; `menu:<item text>` opens an item's menu.
  const menu = name.startsWith("menu:") ? name.slice(5) : null;
  const button = Array.from(document.querySelectorAll<HTMLElement>("button, label")).find((b) => b.textContent?.trim() === (menu ?? name));
  if (button) {
    presses.shift();
    if (menu) button.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    else button.click();
  }
  requestAnimationFrame(pressNext);
};
requestAnimationFrame(pressNext);

createRoot(container).render(
  <div style={{ display: "flex", minHeight: "720px", background: "var(--surface-app)" }}>
    <BoardsPlace
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      caseId={params.get("nocase") ? null : "c1"}
      caseName={params.get("nocase") ? null : "Kestrel"}
      selection={params.get("selection") === "none" ? [] : ["p-mercer", "p-ward"]}
      entityTypes={[{ name: "Person", properties: [{ name: "family_name", type: "string", required: true }, { name: "given_names", type: "string" }] }]}
      markings={MARKINGS}
      mayDraw={reader !== "rita"}
      initialBoard={params.get("board")}
      onCaseMade={(caseId, boardId) => (window.__BOARDS__!.caseMade = { caseId, boardId })}
    />
  </div>,
);
