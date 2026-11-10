// A drawn watch's alert keyboard harness (ADR-143 Amendment 2 decision 8; L3.6; rule 13): the one
// queue holding a load's match on the drawn item *Tall*, as its owner reads it. The Conduit is a
// stand-in kept here, answering the queue and the alert's explanation as the queue's routes do (the
// explanation holds the drawn item, whose provenance names its board). `?open=w1` opens the alert's
// detail at once, for the axe scan. The board *Open the board* asks for is on
// `window.__DRAWN_WATCH__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AlertQueue } from "../src/alerts/AlertQueue";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __DRAWN_WATCH__?: { opened: string[] };
  }
}

window.__DRAWN_WATCH__ = { opened: [] };
const params = new URLSearchParams(window.location.search);

const handling = { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" };
const audit = { created_at: "2026-11-01T00:00:00Z", created_by: "seed", revision: 1 };
const drawn = {
  id: "d1", type: "Person", properties: { family_name: "Tall" }, handling, audit, datasets: ["layer"],
  provenance: { state: "asserted", sources: [], first_seen: "2026-11-01T00:00:00Z",
    drawn: { item_id: "i1", asserted_by: "analyst-1", board_id: "board-7", case_id: "inv-1", label: "Tall",
             grading: { scheme: "3x5x2", source: "B", intelligence: "2", handling: "P" } } },
};  // prettier-ignore
const loaded = {
  id: "p1", type: "Person", properties: { family_name: "TALL", given_names: "Jordan" }, handling, audit,
  datasets: ["src"], provenance: { state: "asserted", sources: [{ document_id: "in/nominals.csv", locator: "row 3",
  excerpt_hash: "a" }], first_seen: "2026-11-01T00:00:00Z" },
};  // prettier-ignore
const row = {
  alert: { id: "w1", rule_id: "drawn_watch:watch-1", owner_id: "analyst-1", mode: "full", investigation_id: "inv-1",
           assignee: null, created_at: "2026-11-10T07:00:00Z", referent_node_ids: ["d1", "p1"], status: "open",
           dataset_id: "src", words: "A load met a drawn item: p1 looks like d1 (the same pnc_id)." },
  summary: "A load met a drawn item: Jordan TALL looks like Tall (the same pnc_id).",
  kind: "drawn_watch", severity: "medium", audience: "owner", team: null,
};  // prettier-ignore

window.fetch = async (input: RequestInfo | URL) => {
  const path = new URL(String(input)).pathname.replace("/v1/investigations/inv-1/", "");
  const reply = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  if (path === "alert-queue") return reply([row]);
  if (path === "alert-queue/w1") return reply({ ...row, nodes: [drawn, loaded], edges: [], transactions: [] });
  return reply({ detail: "not found" }, 404);
};

await applyHarnessBrand();

createRoot(document.getElementById("root")!).render(
  <AlertQueue
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    level="editor"
    accountId="analyst-1"
    onCanvas={() => undefined}
    openAlertId={params.get("open")}
    onOpenBoard={(boardId) => {
      window.__DRAWN_WATCH__!.opened.push(boardId);
    }}
  />,
);
